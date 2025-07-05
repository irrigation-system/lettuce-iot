import board
import busio
import RPi.GPIO as GPIO

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from adafruit_extended_bus import ExtendedI2C

import paho.mqtt.client as mqtt
import requests
import json

import calendar
from datetime import datetime, timedelta
import time

from models import Weather, Crop, IrrigationData


i2c_1 = busio.I2C(board.SCL, board.SDA)
ads_moisture = ADS.ADS1115(i2c_1)
moisture_chan = AnalogIn(ads_moisture, ADS.P0)

i2c_3 = ExtendedI2C(3)
ads_tds = ADS.ADS1115(i2c_3)
tds_chan = AnalogIn(ads_moisture, ADS.P0)

water_switch_pin = 13
fertilizer_switch_pin = 6

# calibration values
# 21198.4
dry_soil_val = 20000
wet_soil_val = 25000

optimal_tds = 600

# mqtt configuration
MQTT_BROKER = "192.168.0.224"
MQTT_PORT = 1883
MQTT_TOPIC = "sensor-data"
USER_TOKEN = "TOKEN"


def initialize_system():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(water_switch_pin, GPIO.OUT)
    GPIO.setup(fertilizer_switch_pin, GPIO.OUT)
    
    # pumps should be switched off at start 
    GPIO.output(water_switch_pin, GPIO.LOW)
    GPIO.output(fertilizer_switch_pin, GPIO.LOW)
    
    return

def read_soil_moisture_percent(num_of_samples=50, discard=10):
    
    readings = []
    
    try: 
        for _ in range(discard):
            _ = moisture_chan.value
        
        for _ in range(num_of_samples):
            val = moisture_chan.value
            readings.append(val)
            time.sleep(0.001)
            
        soil_val = sum(readings) / len(readings)

        moisture = 100 * (soil_val - dry_soil_val) / (wet_soil_val - dry_soil_val)
        moisture = max(0, min(100, moisture))  # Clamp to 0?100
        
        print(f"[{datetime.now().isoformat()}] READ soil moisture: {moisture:.1f}%, soil val: {soil_val}")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ERROR Failed reading soil moisture: {e}")
        return -1
    
    return moisture

def read_TDS(num_of_samples=50, discard=50):
    
    readings = []
    
    try: 
        for _ in range(discard):
            _ = tds_chan.voltage
        
        for _ in range(num_of_samples):
            val = tds_chan.voltage
            readings.append(val)
            time.sleep(0.001)
            
        tds_voltage = sum(readings) / len(readings)
        
        tds_value = (tds_voltage * 1000) / 5 * 1.5 

        print(f"[{datetime.now().isoformat()}] READ TDS: {tds_value:.2f} ppm, ,voltage: {tds_voltage:.3f} V")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ERROR Failed reading soil TDS: {e}")
        return -1
    
    return tds_value

def send_soil_moisture_and_TDS_to_service(soil_moisture: float, tds: float):
    
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "soilMoisture": soil_moisture,
        "tds": tds,
        "user": {
            "userToken": USER_TOKEN
        }
    }
    print(f"[{datetime.now().isoformat()}] SEND MQTT message: {payload}")
    
    payload_str = json.dumps(payload)
    
    client = mqtt.Client()
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.publish(MQTT_TOPIC, payload_str)
        client.disconnect()

    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ERROR Failed to send MQTT message: {e}")
    return
    
def get_weather():
    
    rainfall = 0
    et_ref = 0
    
    url = "http://192.168.0.118:8080/api/v1/weather?userToken=" + USER_TOKEN

    rainfall = None
    et_ref = None
    try:
        response = requests.get(url)
        response.raise_for_status()

        weather_data = response.json()

        weather = Weather.from_dict(weather_data)
        
        rainfall = weather.rainfall_mm
        et_ref = weather.et_ref

        print(f"[{datetime.now().isoformat()}] FETCHED weather data: {weather}")

    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now().isoformat()}] ERROR fetching data: {e}")
    
    
    return rainfall, et_ref

def get_crop_info():
    
    url = "http://192.168.0.118:8080/api/v1/crop?userToken=" + USER_TOKEN

    crop_info = None
    try:
        response = requests.get(url)
        response.raise_for_status()

        crop_info = Crop.from_dict(response.json())

        print(f"[{datetime.now().isoformat()}] FETCHED crop data: {crop_info}")

    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now().isoformat()}] ERROR fetching data: {e}")
    
    return crop_info

def get_irrigation_data_for_user():
    
    url = "http://192.168.0.118:8080/api/v1/irrigation?userToken=" + USER_TOKEN

    irrigation_info = None
    try:
        response = requests.get(url)
        response.raise_for_status()

        irrigation_info = IrrigationData.from_dict(response.json())

        print(f"[{datetime.now().isoformat()}] FETCHED irrigation data: {irrigation_info}")

    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now().isoformat()}] ERROR fetching data: {e}")
    
    return irrigation_info

def calculate_required_water(ET_ref: float, crop: Crop, irrigation_info : IrrigationData):
    
    K_c = get_crop_coefficient(crop, irrigation_info.irrigation_start)
    ET_crop = ET_ref * K_c
    
    P = irrigation_info.monthly_rainfall
    Pe = 0.8 * P - 25
    if P < 75:
        Pe = 0.6 * P - 10
    
    Pe = Pe/30
    
    required_water = ET_crop - Pe # liters by square meter 
    
    required_water = round(required_water * irrigation_info.cultivation_area, 2)
    
    print(f"[{datetime.now().isoformat()}] CALCULATED required irrigation water: {required_water} mm/day (et_ref: {ET_ref}, Pe: {Pe})")
    return required_water


def get_crop_coefficient(crop: Crop, irrigation_start: IrrigationData) -> float:
    
    days_since_irrigation_start = (datetime.now().date() - irrigation_start.date()).days
    
    if days_since_irrigation_start < 0:
        raise ValueError(f"[{datetime.now().isoformat()}] ERROR Irrigation start date is in the future.")
    
    thresholds = [
        crop.dev_num_of_days,
        crop.dev_num_of_days + crop.mid_num_of_days,
        crop.dev_num_of_days + crop.mid_num_of_days + crop.lat_num_of_days 
        ]
    
    coefficients = [
        crop.coefficient_dev,
        crop.coefficient_mid,
        crop.coefficient_late
        ]
    
    for threshold, coefficient in zip(thresholds, coefficients):
        if days_since_irrigation_start <= threshold:
            return coefficient 
    

def supply_water(required_water, min_allowed_moisture, flow_rate = 1.750):
    
    sensor_check_interval = 5 # check soil moisture every 5 seconds 
    irrigation_duration = (required_water/flow_rate) * 60
    
    print(f"[{datetime.now().isoformat()}] CALCULATED irrigation duration: {irrigation_duration}")
    
    GPIO.output(water_switch_pin, GPIO.HIGH) # valve ON
    
    start_time = time.time()
    soil_moisture = 0
    last_moisture_check = start_time
    while True:
        current_time = time.time()
        
        elapsed = current_time - start_time
        
        if current_time - last_moisture_check >= sensor_check_interval:
            soil_moisture = read_soil_moisture_percent()
            last_moisture_check = current_time
        
        if elapsed >= irrigation_duration or soil_moisture > min_allowed_moisture:

            GPIO.output(water_switch_pin, GPIO.LOW) # valve OFF
            
            required_water = max(0, ((irrigation_duration - elapsed) / 60) * flow_rate)
            
            print(f"[{datetime.now().isoformat()}] INFO Water supplied. Remaining water for today: {required_water}")
            return required_water
    
        time.sleep(0.1) # sleep to avoid busy waiting    
    
    
    return

def supply_fertilizer(tds, required_water, fertilizer_per_liter=0.015, flow_rate = 1.750):

    fertilizer_needed = required_water * fertilizer_per_liter
    fertilization_duration = (fertilizer_needed/flow_rate) * 60
    print(f"[{datetime.now().isoformat()}] CALCULATED fertilizer needed: {fertilizer_needed}")
    print(f"[{datetime.now().isoformat()}] CALCULATED fertilization duration: {fertilization_duration}")
    
    GPIO.output(fertilizer_switch_pin, GPIO.HIGH) # valve ON
    
    start_time = time.time()
    
    while True:
        current_time = time.time()
        elapsed = current_time - start_time
        
        if tds >= optimal_tds or elapsed >= fertilization_duration:
            GPIO.output(fertilizer_switch_pin, GPIO.LOW) # valve OFF
            print(f"[{datetime.now().isoformat()}] INFO Fertilizer supplied. Optimal tds value reached. TDS value: {tds}")
            break
        
        time.sleep(0.1) # sleep to avoid busy waiting
        tds = read_TDS()
    
    return

def loop():
    
    required_water = 0;
    last_water_calc_time = datetime(2000, 1, 1)
    last_fertilizer_added_time = datetime(2000, 1, 1)
    
    while True:

        soil_moisture = read_soil_moisture_percent()
        
        if soil_moisture == -1:
            print(f"[{datetime.now().isoformat()}] ERROR Unable to read soil moisture, waiting for 5 min.")
            time.sleep(5 * 60)
            continue
            
        tds = read_TDS()
        
        send_soil_moisture_and_TDS_to_service(soil_moisture, tds)
        
        rainfall, et_ref = get_weather()
        if rainfall is None or et_ref is None:
            print(f"[{datetime.now().isoformat()}] INFO API unavailable, waiting for 15 min.")
            time.sleep(15 * 60)
            continue
            
        crop_info = get_crop_info()
        if crop_info is None:
            print(f"[{datetime.now().isoformat()}] INFO API unavailable, waiting for 15 min..")
            time.sleep(15 * 60)
            continue
        
        if soil_moisture < crop_info.min_allowed_moisture and rainfall == 0:
            print(f"[{datetime.now().isoformat()}] INFO soil moisture ({soil_moisture}) < min_allowed ({crop_info.min_allowed_moisture}) and no rain.")
            
            duration_since_last_irrigation = datetime.now() - last_water_calc_time   
            
            irrigation_info = get_irrigation_data_for_user()
            if irrigation_info is None:
                print(f"[{datetime.now().isoformat()}] INFO API unavailable, waiting for 15 min..")
                time.sleep(15 * 60)
                continue
            
            if duration_since_last_irrigation >= timedelta(hours=24):
                required_water = calculate_required_water(et_ref, crop_info, irrigation_info)
                last_water_calc_time = datetime.now()
                            
            if required_water > 0:
                print(f"[{datetime.now().isoformat()}] INFO Supplying water")
                new_required_water = supply_water(required_water, crop_info.min_allowed_moisture)
                
                # add fertilizer to water 
                duration_since_last_fertilization = datetime.now() - last_fertilizer_added_time
        
                if duration_since_last_fertilization >= timedelta(hours=168):
                    print(f"[{datetime.now().isoformat()}] INFO A week passed, add fertilizer")
                    water_supplied = required_water - new_required_water
                    supply_fertilizer(tds, water_supplied)
                    last_fertilizer_added_time = datetime.now()
                required_water = new_required_water
                
        else:
            print(f"[{datetime.now().isoformat()}] INFO No water supplied. Soil moisture: {soil_moisture}, rainfall: {rainfall} ")
        
        time.sleep(30 * 60) # 30 min sleep

def destroy():
    GPIO.cleanup()
    return 


if __name__=="__main__":
    
    initialize_system()
    
    try:
        loop()
    except KeyboardInterrupt:
        print("Turning device OFF")
        destroy()