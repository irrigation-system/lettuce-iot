import board
import busio

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

dry_soil_val = 21200
wet_soil_val = 22040

# mqtt configuration
MQTT_BROKER = "192.168.0.224"
MQTT_PORT = 1883
MQTT_TOPIC = "sensor-data"
USER_TOKEN = "123"


def read_soil_moisture_percent():

    soil_val = moisture_chan.value
    moisture = 100 * (soil_val - dry_soil_val) / (wet_soil_val - dry_soil_val)
    
    print(f"Soil moisture: {moisture:.1f}%")
    
    return moisture

def read_TDS():
    
    tds_voltage = tds_chan.voltage
    tds_value = (tds_voltage * 1000) / 5 * 1.5 

    print(f"TDS Voltage: {tds_voltage:.3f} V")
    print(f"TDS: {tds_value:.2f} ppm")
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
    print(f"Sending MQTT message: {payload}")
    
    payload_str = json.dumps(payload)
    
    client = mqtt.Client()
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.publish(MQTT_TOPIC, payload_str)
        client.disconnect()

    except Exception as e:
        print(f"Failed to send MQTT message: {e}")
    return
    
def get_weather():
    
    rainfall = 0
    et_ref = 0
    
    url = "TODO"

    try:
        response = requests.get(url)
        response.raise_for_status()

        weather_data = response.json()

        weather = Weather.from_dict(weather_data)

        print(f"Rainfall (mm): {weather.rainfall}")
        print(f"ET Reference: {weather.et_ref}")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    
    
    return weather.rainfall, weather.et_ref

def get_crop_info():
    
    url = "TODO"

    try:
        response = requests.get(url)
        response.raise_for_status()

        crop_info = Crop.from_dict(response.json())

        print(f"Min allowed moisture: {crop_info.min_allowed_moisture}")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    
    return crop_info

def get_irrigation_data_for_user():
    
    url = "TODO"

    try:
        response = requests.get(url)
        response.raise_for_status()

        irrigation_info = IrrigationData.from_dict(response.json())

        print(f"Irrigation info : {irrigation_info.irrigation_start}")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    
    return irrigation_info

def calculate_required_water(ET_ref: float, crop: Crop, irrigation_data : IrrigationData):
    
    K_c = get_crop_coefficient(crop, irrigation_data.irrigation_start)
    print(f"Coefficient:  {K_c}")
    print(f"et ref:  {ET_ref}")
    ET_crop = ET_ref * K_c
    print(f"et crop:  {ET_crop}")
    
    # this should be changed to by day instead of by month 
    P = irrigation_data.monthly_rainfall
    Pe = 0.8 * P - 25
    if P < 75:
        Pe = 0.6 * P - 10
    
    Pe = Pe/30
    print(f"Pe should always be nonnegative:  {Pe}")
    
    required_water = ET_crop - Pe # value by square meter 
    
    required_water = round(required_water * irrigation_data.cultivation_area, 2)
    
    return required_water


def get_crop_coefficient(crop: Crop, irrigation_start: IrrigationData) -> float:
    
    days_since_irrigation_start = (datetime.now().date() - irrigation_start.date()).days
    print(f"Date time now:  {datetime.now().date()}")
    print(f"Irrigation start date :  {irrigation_start.date()}")
    print(f"Days since irrigation start:  {days_since_irrigation_start}")
    
    if days_since_irrigation_start < 0:
        raise ValueError("Irrigation start date is in the future.")
    
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
    

def supply_water(required_water):
    
    water_flow_rate = 1 # 1 L/min - TODO measure right value 
    irrigation_duration = (required_water/water_flow_rate) * 60
    
    # TODO turn ON valve 

    start_time = time.time()
    while True:
        #check if soil moisture is greater than min allowed,
        
        elapsed = time.time() - start_time
        if elapsed >= irrigation_duration:
            # turn valve off 
            # calculate the remainingrequired water 
            # return the remaining required water 
            print(f"Timer over for: {irrigation_duration}")
            break
        # sleep to avoid busy waiting
        time.sleep(0.1)
    
    
    return

def supply_fertilizer(tds):
    # TODO is TDS too low
    # then turn the valve on until its high enough
    
    return

def loop():
    
    required_water = 0;
    last_water_calc_time = datetime(2000, 1, 1)
    
    while True:

        soil_moisture = read_soil_moisture_percent()
        
        tds = read_TDS()
        
        send_soil_moisture_and_TDS_to_service(soil_moisture, tds)
        
        rainfall = 0 # TODO remove once GET weather endpoin is in place
        et_ref = 5.0 # TODO remove once GET weather endpoin is in place
        #rainfall, etRef = get_weather()
        
        crop_info = Crop(
            name="Lettuce",
            min_allowed_moisture=1000.0,
            coefficient_dev=1.0,
            coefficient_mid=1.1,
            coefficient_late=0.9,
            dev_num_of_days=30,
            mid_num_of_days=40,
            lat_num_of_days=20
        ) # TODO remove once get crop endpoint is in place 
        # crop_info = get_crop_info()

        supply_fertilizer(tds)
        
        
        if soil_moisture < crop_info.min_allowed_moisture and rainfall == 0:
            current_time = datetime.now()
            time_diff = current_time - last_water_calc_time
            print(f" {time_diff}")
            
            
            irrigation_info = IrrigationData(
                irrigation_start=datetime(2025,6,20),
                monthly_rainfall_month="May",
                monthly_rainfall=54,
                cultivation_area=0.21
            ) # TODO remove once irrgation endpoint is in place 
            # irrigation_info = get_irrigation_data_for_user()
            
            if time_diff >= timedelta(hours=24):
                required_water = calculate_required_water(et_ref, crop_info, irrigation_info)
                
                last_water_calc_time = datetime.now()
                print(f"Water requirement calculated at: {last_water_calc_time}")
                print(f"Required water: {required_water}")
                            
            if required_water > 0:
                supply_water(required_water)
        
        # 15 min sleep 
        time.sleep(15 * 60)

def destroy():
    return 


if __name__=="__main__":
    
    try:
        loop()
    except KeyboardInterrupt:
        print("Turning device OFF")
        destroy()