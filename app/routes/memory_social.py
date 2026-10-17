"""Family-only memory comments/reactions, with per-account opt-in notifications."""
import hmac
from datetime import datetime, timezone

from flask import Blueprint, abort, g, jsonify, request, session
from sqlalchemy import func
from app.db_queries import get_items_by_type, get_setting_by_name, get_user_setting
from app.logger import log
from app.models import MemoryComment, MemoryReaction, SessionLocal, User
from app.notifications import send_notification
from app.permissions import has_list_permission
from app.routes.auth import jwt_required

social_bp = Blueprint('memory_social', __name__)
REACTIONS = ('heart', 'like', 'laugh', 'celebrate')


def _visible_item(item_id):
    if not has_list_permission('View', 'Home'):
        abort(403)
    visible = {item.id: item for item, _ in get_items_by_type(
        1, edition=get_setting_by_name('sm_edition').value
    )}
    if item_id not in visible:
        abort(404)
    return visible[item_id]


def _csrf():
    expected = session.get('memory_social_csrf', '')
    received = request.headers.get('X-CSRF-Token', '')
    return bool(expected and received and request.cookies.get('jwt_token') and request.is_json
                and hmac.compare_digest(expected, received))


def _notify_owner(item, actor_id, summary):
    if item.createdByUser == actor_id:
        return
    preference = get_user_setting(item.createdByUser, 'notification_engagement_enabled')
    if not preference or preference.value != 'True':
        return
    try:
        # Do not send comment text or memory contents to email/third-party channels.
        send_notification(item.createdByUser, 'SharedMoments activity', summary)
    except Exception as exc:
        log('warning', f'Memory notification failed: {type(exc).__name__}')


@social_bp.route('/api/v2/memories/<int:item_id>/engagement', methods=['GET'])
@jwt_required
def engagement(item_id):
    _visible_item(item_id)
    db = SessionLocal()
    try:
        comments = db.query(MemoryComment, User).join(
            User, MemoryComment.authorID == User.id
        ).filter(MemoryComment.itemID == item_id).order_by(
            MemoryComment.createdAt.asc(), MemoryComment.id.asc()
        ).limit(200).all()
        reactions = db.query(
            MemoryReaction.kind, func.count(MemoryReaction.id)
        ).filter_by(itemID=item_id).group_by(MemoryReaction.kind).all()
        own = [row.kind for row in db.query(MemoryReaction).filter_by(
            itemID=item_id, userID=g.user_id
        )]
        return jsonify({'status':'success', 'data':{
            'comments': [
                {'id': comment.id, 'content': comment.content,
                 'author': f'{user.firstName or ""} {user.lastName or ""}'.strip(),
                 'created': comment.createdAt.isoformat() if comment.createdAt else None,
                 'mine': comment.authorID == g.user_id,
                 'can_delete': (comment.authorID == g.user_id
                                or has_list_permission('Delete','Home'))}
                for comment,user in comments
            ],
            'reactions': {kind: dict(reactions).get(kind,0) for kind in REACTIONS},
            'mine': own,
        }})
    finally:
        db.close()


@social_bp.route('/api/v2/memories/<int:item_id>/comments', methods=['POST'])
@jwt_required
def add_comment(item_id):
    item = _visible_item(item_id)
    if not has_list_permission('Create', 'Home') or not _csrf():
        abort(403)
    payload = request.get_json(silent=True) or {}
    content = payload.get('content')
    if not isinstance(content,str) or not 1 <= len(content.strip()) <= 1200:
        return jsonify({'status':'error', 'message':'Comment must be 1–1200 characters'}),400
    db = SessionLocal()
    try:
        if db.query(MemoryComment).filter_by(itemID=item_id).count() >= 1000:
            return jsonify({'status':'error','message':'Comment limit reached'}),400
        comment = MemoryComment(itemID=item_id, authorID=g.user_id, content=content.strip())
        db.add(comment)
        db.commit()
        reply = {'status':'success','data':{'id':comment.id}}
    finally:
        db.close()
    _notify_owner(item, g.user_id, 'A family member commented on a shared memory.')
    return jsonify(reply), 201


@social_bp.route('/api/v2/memories/comments/<int:comment_id>', methods=['PATCH','DELETE'])
@jwt_required
def update_comment(comment_id):
    if not _csrf():
        abort(403)
    db = SessionLocal()
    try:
        comment = db.get(MemoryComment, comment_id)
        if not comment:
            abort(404)
        _visible_item(comment.itemID)
        if comment.authorID != g.user_id and not has_list_permission('Delete','Home'):
            abort(403)
        if request.method == 'PATCH':
            if comment.authorID != g.user_id:
                abort(403)
            content = (request.get_json(silent=True) or {}).get('content')
            if not isinstance(content,str) or not 1 <= len(content.strip()) <= 1200:
                return jsonify({'status':'error','message':'Invalid comment'}),400
            comment.content = content.strip()
            comment.editedAt = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            db.delete(comment)
        db.commit()
    finally:
        db.close()
    return jsonify({'status':'success'})


@social_bp.route('/api/v2/memories/<int:item_id>/reactions/<kind>', methods=['PUT'])
@jwt_required
def set_reaction(item_id, kind):
    item = _visible_item(item_id)
    if not _csrf():
        abort(403)
    if kind not in REACTIONS or not isinstance((request.get_json(silent=True) or {}).get('active'),bool):
        return jsonify({'status':'error','message':'Invalid reaction'}),400
    active = request.get_json()['active']
    db = SessionLocal()
    added = False
    try:
        existing = db.query(MemoryReaction).filter_by(
            itemID=item_id,userID=g.user_id,kind=kind
        ).first()
        if active and not existing:
            db.add(MemoryReaction(itemID=item_id,userID=g.user_id,kind=kind))
            added = True
        elif not active and existing:
            db.delete(existing)
        db.commit()
    finally:
        db.close()
    if added:
        _notify_owner(item,g.user_id,'A family member reacted to a shared memory.')
    return jsonify({'status':'success','data':{'active':active}})
