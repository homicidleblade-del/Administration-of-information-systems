# app/models.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import Mapped, relationship
from datetime import date
from typing import List, Optional

db = SQLAlchemy()

# =============== РОЛИ И ПОЛЬЗОВАТЕЛИ ===============
class Role(db.Model):
    """Роли пользователей системы: tenant, accountant, admin"""
    __tablename__ = 'roles'

    id: Mapped[int] = db.Column(db.Integer, primary_key=True)
    name: Mapped[str] = db.Column(db.String(20), unique=True, nullable=False)

    def __repr__(self):
        return f"<Role {self.name}>"


class User(db.Model):
    """Пользователи системы с привязкой к роли"""
    __tablename__ = 'users'

    id: Mapped[int] = db.Column(db.Integer, primary_key=True)
    login: Mapped[str] = db.Column(db.String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = db.Column(db.String(128), nullable=False)  # для учебных целей plain-text допустим
    role_id: Mapped[int] = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)

    role: Mapped["Role"] = relationship("Role", lazy="joined")

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'login': self.login,
            'role': self.role.name if self.role else None
        }

# =============== ОСНОВНЫЕ СУЩНОСТИ ===============
class Region(db.Model):
    """Регион (город, район)"""
    __tablename__ = 'regions'

    id: Mapped[int] = db.Column(db.Integer, primary_key=True)
    name: Mapped[str] = db.Column(db.String(100), nullable=False)
    timezone: Mapped[str] = db.Column(db.String(50), nullable=False)

    buildings:  Mapped[List["Building"]] = relationship("Building", back_populates="region", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {'id': self.id, 'name': self.name, 'timezone': self.timezone}


class Tariff(db.Model):
    """Тариф на электроэнергию"""
    __tablename__ = 'tariffs'

    id: Mapped[int] = db.Column(db.Integer, primary_key=True)
    name: Mapped[str] = db.Column(db.String(100), nullable=False)
    rate_per_kwh: Mapped[float] = db.Column(db.Float, nullable=False)
    valid_from: Mapped[date] = db.Column(db.Date, nullable=False)
    valid_to: Mapped[Optional[date]] = db.Column(db.Date, nullable=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'rate_per_kwh': self.rate_per_kwh,
            'valid_from': self.valid_from.isoformat(),
            'valid_to': self.valid_to.isoformat() if self.valid_to else None
        }


class Building(db.Model):
    """Объект учёта (дом, предприятие), принадлежащий пользователю"""
    __tablename__ = 'buildings'

    id: Mapped[int] = db.Column(db.Integer, primary_key=True)
    name: Mapped[str] = db.Column(db.String(150), nullable=False)
    address: Mapped[str] = db.Column(db.String(255), nullable=False)
    type: Mapped[str] = db.Column(db.String(50), nullable=False)
    region_id: Mapped[int] = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=False)
    tariff_id: Mapped[int] = db.Column(db.Integer, db.ForeignKey('tariffs.id'), nullable=False)
    user_id: Mapped[int] = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    region: Mapped["Region"] = relationship("Region", back_populates="buildings")
    tariff: Mapped["Tariff"] = relationship("Tariff")
    meters: Mapped[List["Meter"]] = relationship("Meter", back_populates="building", cascade="all, delete-orphan")
    owner: Mapped["User"] = relationship("User")

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'type': self.type,
            'region_id': self.region_id,
            'tariff_id': self.tariff_id,
            'user_id': self.user_id,
            'region_name': self.region.name if self.region else None,
            'tariff_name': self.tariff.name if self.tariff else None,
            'owner_login': self.owner.login if self.owner else None
        }


class Meter(db.Model):
    """Счётчик электроэнергии"""
    __tablename__ = 'meters'

    id: Mapped[int] = db.Column(db.Integer, primary_key=True)
    serial_number: Mapped[str] = db.Column(db.String(100), unique=True, nullable=False)
    installation_date: Mapped[date] = db.Column(db.Date, nullable=False)
    building_id: Mapped[int] = db.Column(db.Integer, db.ForeignKey('buildings.id'), nullable=False)

    building: Mapped["Building"] = relationship("Building", back_populates="meters")
    records: Mapped[List["ConsumptionRecord"]] = relationship("ConsumptionRecord", back_populates="meter", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'serial_number': self.serial_number,
            'installation_date': self.installation_date.isoformat(),
            'building_id': self.building_id,
            'building_name': self.building.name if self.building else None
        }


class ConsumptionRecord(db.Model):
    """Запись потребления электроэнергии за период"""
    __tablename__ = 'consumption_records'

    id: Mapped[int] = db.Column(db.Integer, primary_key=True)
    meter_id: Mapped[int] = db.Column(db.Integer, db.ForeignKey('meters.id'), nullable=False)
    period_start: Mapped[date] = db.Column(db.Date, nullable=False)
    period_end: Mapped[date] = db.Column(db.Date, nullable=False)
    consumption_kwh: Mapped[float] = db.Column(db.Float, nullable=False)

    meter: Mapped["Meter"] = relationship("Meter", back_populates="records")

    def to_dict(self) -> dict:
        cost = None
        if self.meter and self.meter.building and self.meter.building.tariff:
            rate = self.meter.building.tariff.rate_per_kwh
            if rate is not None:
                cost = self.consumption_kwh * rate

        return {
            'id': self.id,
            'meter_id': self.meter_id,
            'period_start': self.period_start.isoformat(),
            'period_end': self.period_end.isoformat(),
            'consumption_kwh': self.consumption_kwh,
            'meter_serial': self.meter.serial_number if self.meter else None,
            'building_name': self.meter.building.name if self.meter and self.meter.building else None,
            'estimated_cost_rub': round(cost, 2) if cost is not None else None
        }