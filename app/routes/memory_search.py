"""Search visible Home posts by text, author, date, tags and media type."""
import json
import re
import secrets
import hmac
from datetime import date, datetime
from urllib.parse import urlencode

from flask import Blueprint, abort, g, jsonify, render_template, request, session
from sqlalchemy.exc import IntegrityError
from app.db_queries import get_all_list_types, get_items_by_type, get_setting_by_name, get_user_setting, get_user_by_id
from app.models import MemoryTag, SavedMemorySearch, SessionLocal
from app.permissions import has_list_permission
from app.routes.auth import jwt_required

search_bp = Blueprint('memory_search', __name__)
VALID_MEDIA = ('any', 'photo', 'video', 'gallery', 'text')
TAG_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]{0,31}$')


def _visible():
    return get_items_by_type(1, edition=get_setting_by_name('sm_edition').value)


def _filters(args):
    q = str(args.get('q', '')).strip()
    tag = str(args.get('tag', '')).strip().lower()
    author = str(args.get('author', '')).strip()
    media = str(args.get('media', 'any')).strip() or 'any'
    if len(q) > 150 or (tag and not TAG_PATTERN.fullmatch(tag)):
        raise ValueError('Invalid search text or tag')
    if author and (not author.isdecimal() or len(author) > 10):
        raise ValueError('Invalid author')
    if media not in VALID_MEDIA:
        raise ValueError('Invalid media filter')
    result = {'q': q, 'tag': tag, 'author': author, 'media': media}
    for key in ('date_from', 'date_to'):
        val = str(args.get(key, '')).strip()
        if val and date.fromisoformat(val).isoformat() != val:
            raise ValueError('Invalid date')
        result[key] = val
    if result['date_from'] and result['date_to'] and result['date_from'] > result['date_to']:
        raise ValueError('Date range reversed')
    return result


def _search(visible, fields):
    ids = [item.id for item, _ in visible]
    by_item = {}
    db = SessionLocal()
    try:
        if ids:
            for tag in db.query(MemoryTag).filter(MemoryTag.itemID.in_(ids)):
                by_item.setdefault(tag.itemID, []).append(tag.tag)
    finally:
        db.close()
    matches = []
    for item, creator in visible:
        timestamp = item.dateCreated
        day = (timestamp.date() if isinstance(timestamp, datetime) else timestamp)
        day = day.isoformat() if day else ''
        kind = item.contentType or ''
        wanted = fields['media']
        valid_media = (
            wanted == 'any'
            or (wanted == 'photo' and kind in ('image', 'galleryStartWithImage'))
            or (wanted == 'video' and kind in ('video', 'video-mov', 'galleryStartWithVideo'))
            or (wanted == 'gallery' and kind.startswith('gallery'))
            or (wanted == 'text' and kind == 'text')
        )
        tags = sorted(by_item.get(item.id, []))
        if not valid_media or (fields['q'] and fields['q'].casefold() not in
                 f'{item.title or ""} {item.content or ""}'.casefold()):
            continue
        if fields['tag'] and fields['tag'] not in tags:
            continue
        if fields['author'] and str(item.createdByUser) != fields['author']:
            continue
        if fields['date_from'] and day < fields['date_from']:
            continue
        if fields['date_to'] and day > fields['date_to']:
            continue
        matches.append((item, creator, tags))
    return matches


def _csrf():
    actual = request.headers.get('X-CSRF-Token', '')
    expected = session.get('memory_search_csrf', '')
    return bool(request.is_json and actual and expected and request.cookies.get('jwt_token')
                and hmac.compare_digest(actual, expected))


@search_bp.route('/memories/search')
@jwt_required
def memory_search():
    if not has_list_permission('View', 'Home'):
        abort(403)
    try:
        filters = _filters(request.args)
        page = int(request.args.get('page', '1'))
        if not 1 <= page <= 10000:
            raise ValueError('Invalid page')
    except (ValueError, OverflowError):
        abort(400)

    visible = _visible()
    matches = _search(visible, filters)
    authors = {user.id: f'{user.firstName or ""} {user.lastName or ""}'.strip()
               for item, user in visible}
    db = SessionLocal()
    try:
        saved = [dict(id=x.id, name=x.name, filters=json.loads(x.filters))
                 for x in db.query(SavedMemorySearch).filter_by(userID=g.user_id)
                            .order_by(SavedMemorySearch.name).all()]
        ids = [item.id for item, _ in visible]
        tags = sorted({x.tag for x in db.query(MemoryTag).filter(MemoryTag.itemID.in_(ids))}) if ids else []
    finally:
        db.close()
    from app.routes.pages import get_display_title
    session.setdefault('memory_search_csrf', secrets.token_urlsafe(32))
    return render_template(
        'pages/memory-search.html',
        title=get_display_title(), darkmode=get_user_setting(g.user_id, 'darkmode'),
        user_data=get_user_by_id(g.user_id), list_types=get_all_list_types(),
        filters=filters, authors=authors, tags=tags, saved_searches=saved,
        results=matches[(page-1)*40:page*40], total=len(matches), page=page,
        has_next=len(matches) > page*40,
        csrf_token=session['memory_search_csrf'],
        filter_query=urlencode({key: val for key,val in filters.items() if val and val != 'any'}),
    )


@search_bp.route('/api/v2/memories/<int:item_id>/tags', methods=['PUT'])
@jwt_required
def set_memory_tags(item_id):
    if not has_list_permission('Update', 'Home') or not _csrf():
        abort(403)
    tags = (request.get_json(silent=True) or {}).get('tags')
    if (not isinstance(tags, list) or len(tags) > 12
            or any(not isinstance(x, str) or not TAG_PATTERN.fullmatch(x) for x in tags)
            or len(set(tags)) != len(tags)):
        return jsonify({'status':'error','message':'Tags must be unique lowercase slugs (maximum 12)'}), 400
    if item_id not in {item.id for item, _ in _visible()}:
        abort(404)
    db = SessionLocal()
    try:
        db.query(MemoryTag).filter_by(itemID=item_id).delete()
        db.add_all(MemoryTag(itemID=item_id, tag=x) for x in tags)
        db.commit()
    finally:
        db.close()
    return jsonify({'status':'success','data':{'tags':tags}})


@search_bp.route('/api/v2/memories/saved-searches', methods=['POST'])
@jwt_required
def add_saved_search():
    if not has_list_permission('View', 'Home') or not _csrf():
        abort(403)
    data = request.get_json(silent=True) or {}
    name = str(data.get('name','')).strip()
    if not 1 <= len(name) <= 80 or not isinstance(data.get('filters'), dict):
        return jsonify({'status':'error','message':'Invalid saved search'}),400
    try:
        filters = _filters(data['filters'])
    except (ValueError, OverflowError):
        return jsonify({'status':'error','message':'Invalid filters'}),400
    db = SessionLocal()
    try:
        if db.query(SavedMemorySearch).filter_by(userID=g.user_id).count() >= 40:
            return jsonify({'status':'error','message':'Saved search limit reached'}),400
        record = SavedMemorySearch(userID=g.user_id,name=name,filters=json.dumps(filters))
        db.add(record)
        db.commit()
        return jsonify({'status':'success','data':{'id':record.id}}),201
    except IntegrityError:
        db.rollback()
        return jsonify({'status':'error','message':'Saved search already exists'}),409
    finally:
        db.close()


@search_bp.route('/api/v2/memories/saved-searches/<int:search_id>', methods=['DELETE'])
@jwt_required
def delete_saved_search(search_id):
    if not has_list_permission('View', 'Home') or not _csrf():
        abort(403)
    db = SessionLocal()
    try:
        deleted = db.query(SavedMemorySearch).filter_by(id=search_id,userID=g.user_id).delete()
        db.commit()
    finally:
        db.close()
    if not deleted:
        abort(404)
    return jsonify({'status':'success'})
