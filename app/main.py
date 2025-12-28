# app/main.py
from flask import Flask, request, jsonify
from models import db, Role, User, Region, Tariff, Building, Meter, ConsumptionRecord
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from functools import wraps

# === Добавлено для поддержки CORS ===
from flask_cors import CORS

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://user:password@db:3306/energydb'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# === Инициализация CORS ===
# === Инициализация CORS ===
CORS(app, resources={r"/*": {"origins": "http://localhost:8080"}}, supports_credentials=True)

db.init_app(app)


# ========================
# ДЕКОРАТОР ПРОВЕРКИ РОЛИ
# ========================
def require_role(*allowed_roles):
    """Декоратор для защиты маршрутов по ролям"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = request.headers.get('X-User-ID')
            if not user_id or not user_id.isdigit():
                return jsonify({"error": "Требуется заголовок X-User-ID (целое число)"}), 401

            user = User.query.get(int(user_id))
            if not user:
                return jsonify({"error": "Пользователь не найден"}), 404

            if user.role.name not in allowed_roles:
                return jsonify({"error": "Недостаточно прав"}), 403

            return f(current_user=user, **kwargs)

        return decorated_function

    return decorator


# ========================
# АУТЕНТИФИКАЦИЯ
# ========================
@app.route('/login', methods=['POST'])
def login():
    """Аутентификация пользователя."""
    data = request.get_json()
    login = data.get('login')
    password = data.get('password')

    if not login or not password:
        return jsonify({"error": "Требуются логин и пароль"}), 400

    # Поиск пользователя по логину
    user = User.query.filter_by(login=login).first()
    if not user:
        return jsonify({"error": "Неверный логин или пароль"}), 401

    # Проверка пароля (для учебных целей, plain-text)
    # В реальном приложении здесь должен быть хэш-проверка
    if user.password_hash != password:
        return jsonify({"error": "Неверный логин или пароль"}), 401

    # Успешная аутентификация, возвращаем ID пользователя
    return jsonify({
        "user_id": user.id,
        "login": user.login,
        "role": user.role.name
    }), 200


# ========================
# CLI: ИНИЦИАЛИЗАЦИЯ БД
# ========================
@app.cli.command("init-db")
def init_db_command():
    """Создать таблицы и стандартные роли."""
    with app.app_context():
        db.create_all()
        # Создаём стандартные роли, если их нет
        if not Role.query.filter_by(name='tenant').first():
            db.session.add_all([
                Role(name='tenant'),
                Role(name='accountant'),
                Role(name='admin')
            ])
            db.session.commit()
    print("✅ Таблицы и роли созданы.")


# ========================
# РОЛИ
# ========================
@app.route('/roles', methods=['GET'])
@require_role('admin')
def get_roles(current_user):
    """Получить все роли."""
    return jsonify([r.to_dict() for r in Role.query.all()])


@app.route('/roles/<int:id>', methods=['GET'])
@require_role('admin')
def get_role_by_id(current_user, id):
    """Получить одну роль по ID."""
    role = Role.query.get_or_404(id)
    return jsonify(role.to_dict())


@app.route('/roles', methods=['POST'])
@require_role('admin')
def create_role(current_user):
    """Создать новую роль."""
    data = request.get_json()
    r = Role(name=data['name'])
    db.session.add(r)
    db.session.commit()
    return jsonify(r.to_dict()), 201


# ========================
# ПОЛЬЗОВАТЕЛИ
# ========================
@app.route('/users', methods=['GET'])
@require_role('admin')
def get_users(current_user):
    """Получить всех пользователей."""
    return jsonify([u.to_dict() for u in User.query.all()])


@app.route('/users/<int:id>', methods=['GET'])
@require_role('admin')
def get_user_by_id(current_user, id):
    """Получить одного пользователя по ID."""
    user = User.query.get_or_404(id)
    return jsonify(user.to_dict())


@app.route('/users', methods=['POST'])
@require_role('admin')
def create_user(current_user):
    """Создать нового пользователя."""
    data = request.get_json()
    u = User(
        login=data['login'],
        password_hash=data.get('password_hash', '123'),
        role_id=data['role_id']
    )
    db.session.add(u)
    db.session.commit()
    return jsonify(u.to_dict()), 201


@app.route('/users/<int:id>', methods=['PUT'])
@require_role('admin')
def update_user(current_user, id):
    """Обновить пользователя."""
    if id == current_user.id:
        return jsonify({"error": "Нельзя редактировать самого себя"}), 400

    user = User.query.get_or_404(id)
    data = request.get_json()

    user.login = data.get('login', user.login)
    if 'password_hash' in data:
        user.password_hash = data['password_hash']
    if 'role_id' in data:
        user.role_id = data['role_id']

    db.session.commit()
    return jsonify(user.to_dict())


@app.route('/users/<int:id>', methods=['DELETE'])
@require_role('admin')
def delete_user(current_user, id):
    """Удалить пользователя."""
    if id == current_user.id:
        return jsonify({"error": "Нельзя удалить самого себя"}), 400
    user = User.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    return '', 204


# ========================
# REGIONS
# ========================
@app.route('/regions', methods=['GET'])
@require_role('tenant', 'accountant', 'admin')
def get_regions(current_user):
    """Получить все регионы."""
    return jsonify([r.to_dict() for r in Region.query.all()])


@app.route('/regions/<int:id>', methods=['GET'])
@require_role('tenant', 'accountant', 'admin')
def get_region_by_id(current_user, id):
    """Получить один регион по ID."""
    region = Region.query.get_or_404(id)
    return jsonify(region.to_dict())


@app.route('/regions', methods=['POST'])
@require_role('admin')
def create_region(current_user):
    """Создать новый регион."""
    data = request.get_json()
    r = Region(name=data['name'], timezone=data['timezone'])
    db.session.add(r)
    db.session.commit()
    return jsonify(r.to_dict()), 201


@app.route('/regions/<int:id>', methods=['PUT'])
@require_role('admin')
def update_region(current_user, id):
    """Обновить регион."""
    region = Region.query.get_or_404(id)
    data = request.get_json()
    region.name = data.get('name', region.name)
    region.timezone = data.get('timezone', region.timezone)
    db.session.commit()
    return jsonify(region.to_dict())


@app.route('/regions/<int:id>', methods=['DELETE'])
@require_role('admin')
def delete_region(current_user, id):
    """Удалить регион."""
    region = Region.query.get_or_404(id)
    db.session.delete(region)
    db.session.commit()
    return '', 204


# ========================
# TARIFFS
# ========================
@app.route('/tariffs', methods=['GET'])
@require_role('tenant', 'accountant', 'admin')
def get_tariffs(current_user):
    """Получить все тарифы."""
    return jsonify([t.to_dict() for t in Tariff.query.all()])


@app.route('/tariffs/<int:id>', methods=['GET'])
@require_role('tenant', 'accountant', 'admin')
def get_tariff_by_id(current_user, id):
    """Получить один тариф по ID."""
    tariff = Tariff.query.get_or_404(id)
    return jsonify(tariff.to_dict())


@app.route('/tariffs', methods=['POST'])
@require_role('accountant', 'admin')
def create_tariff(current_user):
    """Создать новый тариф."""
    data = request.get_json()
    valid_to = None
    if data.get('valid_to'):
        try:
            valid_to = datetime.strptime(data['valid_to'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Неверный формат даты valid_to"}), 400

    try:
        valid_from = datetime.strptime(data['valid_from'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Неверный формат даты valid_from"}), 400

    t = Tariff(
        name=data['name'],
        rate_per_kwh=data['rate_per_kwh'],
        valid_from=valid_from,
        valid_to=valid_to
    )
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@app.route('/tariffs/<int:id>', methods=['PUT'])
@require_role('accountant', 'admin')
def update_tariff(current_user, id):
    """Обновить тариф."""
    tariff = Tariff.query.get_or_404(id)
    data = request.get_json()

    tariff.name = data.get('name', tariff.name)
    tariff.rate_per_kwh = data.get('rate_per_kwh', tariff.rate_per_kwh)

    if 'valid_from' in data and data['valid_from']:
        try:
            tariff.valid_from = datetime.strptime(data['valid_from'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Неверный формат даты valid_from"}), 400

    if 'valid_to' in data:
        if data['valid_to']:
            try:
                tariff.valid_to = datetime.strptime(data['valid_to'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"error": "Неверный формат даты valid_to"}), 400
        else:
            tariff.valid_to = None

    db.session.commit()
    return jsonify(tariff.to_dict())


@app.route('/tariffs/<int:id>', methods=['DELETE'])
@require_role('admin')
def delete_tariff(current_user, id):
    """Удалить тариф."""
    tariff = Tariff.query.get_or_404(id)
    db.session.delete(tariff)
    db.session.commit()
    return '', 204


# ========================
# BUILDINGS
# ========================
@app.route('/buildings', methods=['GET'])
@require_role('tenant', 'accountant', 'admin')
def get_buildings(current_user):
    """Получить все здания."""
    if current_user.role.name == 'tenant':
        buildings = Building.query.filter_by(user_id=current_user.id).all()
    else:
        buildings = Building.query.all()
    return jsonify([b.to_dict() for b in buildings])


@app.route('/buildings/<int:id>', methods=['GET'])
@require_role('tenant', 'accountant', 'admin')
def get_building_by_id(current_user, id):
    """Получить одно здание по ID."""
    building = Building.query.get_or_404(id)

    # Проверка прав доступа для tenant
    if current_user.role.name == 'tenant' and building.user_id != current_user.id:
        return jsonify({"error": "Доступ запрещён"}), 403

    return jsonify(building.to_dict())


@app.route('/buildings', methods=['POST'])
@require_role('admin')
def create_building(current_user):
    """Создать новое здание."""
    data = request.get_json()
    b = Building(
        name=data['name'],
        address=data['address'],
        type=data['type'],
        region_id=data['region_id'],
        tariff_id=data['tariff_id'],
        user_id=data['user_id']
    )
    db.session.add(b)
    db.session.commit()
    return jsonify(b.to_dict()), 201


@app.route('/buildings/<int:id>', methods=['PUT'])
@require_role('admin')
def update_building(current_user, id):
    """Обновить здание."""
    building = Building.query.get_or_404(id)
    data = request.get_json()
    building.name = data.get('name', building.name)
    building.address = data.get('address', building.address)
    building.type = data.get('type', building.type)
    building.region_id = data.get('region_id', building.region_id)
    building.tariff_id = data.get('tariff_id', building.tariff_id)
    building.user_id = data.get('user_id', building.user_id)
    db.session.commit()
    return jsonify(building.to_dict())


@app.route('/buildings/<int:id>', methods=['DELETE'])
@require_role('admin')
def delete_building(current_user, id):
    """Удалить здание."""
    building = Building.query.get_or_404(id)
    db.session.delete(building)
    db.session.commit()
    return '', 204


# ========================
# METERS
# ========================
@app.route('/meters', methods=['GET'])
@require_role('tenant', 'accountant', 'admin')
def get_meters(current_user):
    """Получить все счётчики."""
    if current_user.role.name == 'tenant':
        user_building_ids = [b.id for b in Building.query.filter_by(user_id=current_user.id).all()]
        meters = Meter.query.filter(Meter.building_id.in_(user_building_ids)).all()
    else:
        meters = Meter.query.all()
    return jsonify([m.to_dict() for m in meters])


@app.route('/meters/<int:id>', methods=['GET'])
@require_role('tenant', 'accountant', 'admin')
def get_meter_by_id(current_user, id):
    """Получить один счётчик по ID."""
    meter = Meter.query.get_or_404(id)

    # Проверка прав доступа для tenant
    if current_user.role.name == 'tenant':
        building = Building.query.get(meter.building_id)
        if not building or building.user_id != current_user.id:
            return jsonify({"error": "Доступ запрещён"}), 403

    return jsonify(meter.to_dict())


@app.route('/meters', methods=['POST'])
@require_role('admin')
def create_meter(current_user):
    """Создать новый счётчик."""
    data = request.get_json()
    try:
        installation_date = datetime.strptime(data['installation_date'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Неверный формат даты installation_date"}), 400

    m = Meter(
        serial_number=data['serial_number'],
        installation_date=installation_date,
        building_id=data['building_id']
    )
    db.session.add(m)
    db.session.commit()
    return jsonify(m.to_dict()), 201


@app.route('/meters/<int:id>', methods=['PUT'])
@require_role('admin')
def update_meter(current_user, id):
    """Обновить счётчик."""
    meter = Meter.query.get_or_404(id)
    data = request.get_json()
    meter.serial_number = data.get('serial_number', meter.serial_number)

    if 'installation_date' in data and data['installation_date']:
        try:
            meter.installation_date = datetime.strptime(data['installation_date'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Неверный формат даты installation_date"}), 400

    meter.building_id = data.get('building_id', meter.building_id)
    db.session.commit()
    return jsonify(meter.to_dict())


@app.route('/meters/<int:id>', methods=['DELETE'])
@require_role('admin')
def delete_meter(current_user, id):
    """Удалить счётчик."""
    meter = Meter.query.get_or_404(id)
    db.session.delete(meter)
    db.session.commit()
    return '', 204


# ========================
# CONSUMPTION RECORDS
# ========================
@app.route('/consumption', methods=['GET'])
@require_role('tenant', 'accountant', 'admin')
def get_consumption(current_user):
    """Получить все записи потребления."""
    if current_user.role.name == 'tenant':
        building_ids = [b.id for b in Building.query.filter_by(user_id=current_user.id).all()]
        meter_ids = [m.id for m in Meter.query.filter(Meter.building_id.in_(building_ids)).all()]
        records = ConsumptionRecord.query.filter(ConsumptionRecord.meter_id.in_(meter_ids)).all()
    else:
        records = ConsumptionRecord.query.all()
    return jsonify([r.to_dict() for r in records])


@app.route('/consumption/<int:id>', methods=['GET'])
@require_role('tenant', 'accountant', 'admin')
def get_consumption_by_id(current_user, id):
    """Получить одну запись потребления по ID."""
    record = ConsumptionRecord.query.get_or_404(id)

    # Проверка прав доступа для tenant
    if current_user.role.name == 'tenant':
        # Проверяем, принадлежит ли запись tenant
        building_ids = [b.id for b in Building.query.filter_by(user_id=current_user.id).all()]
        meter_ids = [m.id for m in Meter.query.filter(Meter.building_id.in_(building_ids)).all()]

        if record.meter_id not in meter_ids:
            return jsonify({"error": "Доступ запрещён"}), 403

    return jsonify(record.to_dict())


@app.route('/consumption', methods=['POST'])
@require_role('admin', 'accountant')
def create_consumption(current_user):
    """Создать новую запись потребления."""
    data = request.get_json()

    try:
        period_start = datetime.strptime(data['period_start'], '%Y-%m-%d').date()
        period_end = datetime.strptime(data['period_end'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Неверный формат даты period_start или period_end"}), 400

    r = ConsumptionRecord(
        meter_id=data['meter_id'],
        period_start=period_start,
        period_end=period_end,
        consumption_kwh=data['consumption_kwh']
    )
    db.session.add(r)
    db.session.commit()
    return jsonify(r.to_dict()), 201


@app.route('/consumption/<int:id>', methods=['PUT'])
@require_role('admin', 'accountant')
def update_consumption(current_user, id):
    """Обновить запись потребления."""
    record = ConsumptionRecord.query.get_or_404(id)
    data = request.get_json()
    record.meter_id = data.get('meter_id', record.meter_id)

    if 'period_start' in data and data['period_start']:
        try:
            record.period_start = datetime.strptime(data['period_start'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Неверный формат даты period_start"}), 400

    if 'period_end' in data and data['period_end']:
        try:
            record.period_end = datetime.strptime(data['period_end'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Неверный формат даты period_end"}), 400

    record.consumption_kwh = data.get('consumption_kwh', record.consumption_kwh)
    db.session.commit()
    return jsonify(record.to_dict())


@app.route('/consumption/<int:id>', methods=['DELETE'])
@require_role('admin')
def delete_consumption(current_user, id):
    """Удалить запись потребления."""
    record = ConsumptionRecord.query.get_or_404(id)
    db.session.delete(record)
    db.session.commit()
    return '', 204


# ========================
# СТАТИСТИКА И АНАЛИТИКА
# ========================
@app.route('/stats', methods=['GET'])
@require_role('tenant', 'accountant', 'admin')
def get_stats(current_user):
    """Получить статистику по системе."""
    stats = {}

    # Общее количество зданий
    if current_user.role.name == 'tenant':
        stats['total_buildings'] = Building.query.filter_by(user_id=current_user.id).count()
    else:
        stats['total_buildings'] = Building.query.count()

    # Общее количество счетчиков
    if current_user.role.name == 'tenant':
        user_building_ids = [b.id for b in Building.query.filter_by(user_id=current_user.id).all()]
        stats['total_meters'] = Meter.query.filter(Meter.building_id.in_(user_building_ids)).count()
    else:
        stats['total_meters'] = Meter.query.count()

    # Общее потребление
    if current_user.role.name == 'tenant':
        building_ids = [b.id for b in Building.query.filter_by(user_id=current_user.id).all()]
        meter_ids = [m.id for m in Meter.query.filter(Meter.building_id.in_(building_ids)).all()]
        total_consumption = db.session.query(db.func.sum(ConsumptionRecord.consumption_kwh)).filter(
            ConsumptionRecord.meter_id.in_(meter_ids)
        ).scalar() or 0
    else:
        total_consumption = db.session.query(db.func.sum(ConsumptionRecord.consumption_kwh)).scalar() or 0

    stats['total_consumption'] = float(total_consumption)

    # Общая стоимость (примерная)
    stats['total_cost'] = stats['total_consumption'] * 5.50  # Примерная средняя цена

    return jsonify(stats)


# ========================
# ОБРАБОТКА ОШИБОК
# ========================
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({"error": "Ресурс не найден"}), 404


@app.errorhandler(405)
def method_not_allowed_error(error):
    return jsonify({"error": "Метод не разрешен"}), 405


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({"error": "Внутренняя ошибка сервера"}), 500


@app.errorhandler(SQLAlchemyError)
def handle_db_error(e):
    db.session.rollback()
    return jsonify({"error": "Ошибка базы данных", "message": str(e)}), 500


# ========================
# HEALTH CHECK
# ========================
@app.route('/health', methods=['GET'])
def health_check():
    """Проверка работоспособности API."""
    return jsonify({"status": "ok", "message": "API работает"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)