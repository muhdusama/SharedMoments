"""Opt-in map metadata for authorised Home memories; private coordinates stay owner-only."""
import hmac
import math
import secrets

from flask import Blueprint, abort, g, jsonify, render_template, request, session
from app.db_queries import (
    get_all_list_types, get_items_by_type, get_setting_by_name, get_user_setting,
    get_user_by_id,
)
from app.models import MemoryLocation, SessionLocal
from app.permissions import has_list_permission
from app.routes.auth import jwt_required

map_bp = Blueprint('memory_map', __name__)


def _visible():
    return get_items_by_type(1, edition=get_setting_by_name('sm_edition').value)


def _csrf_ok():
    expected = session.get('memory_map_csrf', '')
    supplied = request.headers.get('X-CSRF-Token', '')
    return bool(expected and supplied and request.is_json and request.cookies.get('jwt_token')
                and hmac.compare_digest(expected, supplied))


def _points(visible, current_user):
    ids = [item.id for item, _ in visible]
    if not ids:
        return []
    titles = {item.id: item.title for item, _ in visible}
    db = SessionLocal()
    try:
        locations = db.query(MemoryLocation).filter(MemoryLocation.itemID.in_(ids)).all()
        return [
            {
                'item_id': x.itemID, 'title': titles[x.itemID],
                'lat': x.latitude, 'lng': x.longitude,
                'label': x.label, 'trip': x.trip, 'visibility': x.visibility,
                'owner': x.createdByUser == current_user,
                'url': f'/home#article_{x.itemID}',
            }
            for x in locations
            if x.visibility == 'family' or x.createdByUser == current_user
        ]
    finally:
        db.close()


@map_bp.route('/memories/map')
@jwt_required
def map_page():
    if not has_list_permission('View', 'Home'):
        abort(403)
    visible = _visible()
    points = _points(visible, g.user_id)
    trip = request.args.get('trip', '').strip().casefold()
    place = request.args.get('place', '').strip().casefold()
    if len(trip) > 80 or len(place) > 120:
        abort(400)
    filtered = [point for point in points
                if (not trip or trip in point['trip'].casefold())
                and (not place or place in point['label'].casefold())]
    from app.routes.pages import get_display_title
    session.setdefault('memory_map_csrf', secrets.token_urlsafe(32))
    return render_template(
        'pages/memory-map.html',
        title=get_display_title(), user_data=get_user_by_id(g.user_id),
        darkmode=get_user_setting(g.user_id, 'darkmode'), list_types=get_all_list_types(),
        points=filtered, count=len(filtered), can_edit=has_list_permission('Update','Home'),
        items=[(item.id, item.title or f'Entry {item.id}') for item, _ in visible][:500],
        trip_filter=request.args.get('trip',''),
        place_filter=request.args.get('place',''),
        csrf_token=session['memory_map_csrf'],
    )


@map_bp.route('/api/v2/memories/<int:item_id>/location', methods=['PUT','DELETE'])
@jwt_required
def location_update(item_id):
    if not has_list_permission('Update', 'Home') or not _csrf_ok():
        abort(403)
    if item_id not in {item.id for item, _ in _visible()}:
        abort(404)

    payload = request.get_json(silent=True) or {}
    if request.method == 'PUT':
        try:
            latitude = float(payload['lat'])
            longitude = float(payload['lng'])
        except (ValueError, TypeError, KeyError):
            return jsonify({'status':'error','message':'Valid numeric coordinates are required'}), 400
        if (not math.isfinite(latitude) or not math.isfinite(longitude)
                or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
            return jsonify({'status':'error','message':'Coordinates out of range'}), 400
        label = str(payload.get('label', '')).strip()
        trip = str(payload.get('trip', '')).strip()
        visibility = payload.get('visibility', 'private')
        if len(label) > 120 or len(trip) > 80 or visibility not in ('private','family'):
            return jsonify({'status':'error','message':'Invalid location metadata'}), 400

    db = SessionLocal()
    try:
        record = db.query(MemoryLocation).filter_by(itemID=item_id).first()
        if record and record.visibility == 'private' and record.createdByUser != g.user_id:
            abort(404)
        if request.method == 'DELETE':
            if not record:
                abort(404)
            db.delete(record)
        else:
            if record is None:
                record = MemoryLocation(itemID=item_id, createdByUser=g.user_id)
                db.add(record)
            record.latitude = latitude
            record.longitude = longitude
            record.label = label
            record.trip = trip
            record.visibility = visibility
        db.commit()
    finally:
        db.close()
    return jsonify({'status':'success'})
