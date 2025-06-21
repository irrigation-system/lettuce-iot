from dataclasses import dataclass
from datetime import datetime
from dateutil.parser import parse

@dataclass
class Weather:
    timestamp: datetime
    rainfall_mm: float
    et_ref: float
    humidity: float
    temperature: float

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            timestamp=parse(data["timestamp"]),
            rainfall_mm=data["rainfallmm"],
            et_ref=data["etRef"],
            humidity=data["humidity"],
            temperature=data["temperature"]
        )
    
    
@dataclass
class Crop:
    name: str
    min_allowed_moisture: float
    coefficient_dev: float
    coefficient_mid: float
    coefficient_late: float
    dev_num_of_days: int
    mid_num_of_days: int
    lat_num_of_days: int

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=data["name"],
            min_allowed_moisture=data["minAllowedMoisture"],
            coefficient_dev=data["coefficientDev"],
            coefficient_mid=data["coefficientMid"],
            coefficient_late=data["coefficientLate"],
            dev_num_of_days=data["devNumOfDays"],
            mid_num_of_days=data["midNumOfDays"],
            lat_num_of_days=data["latNumOfDays"],
        )
    
@dataclass
class IrrigationData:
    irrigation_start: datetime
    monthly_rainfall_month: str
    monthly_rainfall: float
    cultivation_area: float

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            irrigation_start=parse(data["irrigationStart"]),
            monthly_rainfall_month=data["monthlyRainfallMonth"],
            monthly_rainfall=data["monthlyRainfall"],
            cultivation_area=data["cultivationArea"],
        )