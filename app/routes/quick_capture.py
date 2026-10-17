"""iOS Shortcuts uploads go to private, per-user drafts until explicit publication."""
import hmac
import os
import secrets
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, g, jsonify, render_template, request, send_file, session
from werkzeug.utils import secure_filename

from app.db_queries import (
    get_all_list_types, get_setting_by_name, get_user_by_id, get_user_setting,
)
from app.models import CaptureDraft, Item, SessionLocal
from app.permissions import has_list_permission
from app.routes.auth import jwt_required

capture_bp = Blueprint('quick_capture', __name__)

IMAGES = frozenset({'jpg','jpeg','png','gif','webp','heic','heif'})
VIDEOS = frozenset({'mov','mp4','webm'})
MAX_BYTES = 512 * 1024 * 1024


def _draft_folder():
    path = Path(__file__).resolve().parent.parent / 'uploads' / 'capture-drafts'
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def _csrf():
    expected = session.get('capture_csrf', '')
    actual = request.headers.get('X-CSRF-Token', '')
    return bool(request.cookies.get('jwt_token') and expected and actual
                and hmac.compare_digest(expected, actual))


@capture_bp.route('/captures')
@jwt_required
def capture_inbox():
    if not has_list_permission('View','Home'):
        abort(403)
    session.setdefault('capture_csrf', secrets.token_urlsafe(32))
    db = SessionLocal()
    try:
        drafts = [
            {'id': x.id, 'title': x.title, 'description': x.description,
             'filename': x.originalFilename, 'status': x.status,
             'mediaType': x.mediaType, 'published': x.publishedItemID}
            for x in db.query(CaptureDraft).filter_by(userID=g.user_id)
                       .order_by(CaptureDraft.id.desc()).limit(200)
        ]
    finally:
        db.close()
    from app.routes.pages import get_display_title
    return render_template(
        'pages/capture-inbox.html',
        title=get_display_title(), user_data=get_user_by_id(g.user_id),
        darkmode=get_user_setting(g.user_id, 'darkmode'),
        list_types=get_all_list_types(), drafts=drafts, csrf_token=session['capture_csrf'],
    )


@capture_bp.route('/api/v2/capture/drafts', methods=['POST'])
@jwt_required
def create_capture_draft():
    if not has_list_permission('Create','Home'):
        abort(403)
    # A dedicated read-write API key from PR #20 is accepted via the existing
    # app's bearer auth middleware. Cookie callers must also present CSRF.
    if not getattr(g, 'api_key_auth', False) and not _csrf():
        abort(403)
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'status':'error','message':'One file is required'}),400
    if len(request.files.getlist('file')) != 1:
        return jsonify({'status':'error','message':'Send each file separately'}),400
    original = secure_filename(file.filename)[:160]
    extension = Path(original).suffix.lower().lstrip('.')
    if not original or extension not in IMAGES | VIDEOS:
        return jsonify({'status':'error','message':'Unsupported file type'}),400
    title = str(request.form.get('title') or Path(original).stem).strip()[:255]
    description = str(request.form.get('description','')).strip()
    if not title or len(description) > 4000:
        return jsonify({'status':'error','message':'Invalid draft description'}),400
    requested_date = request.form.get('date','').strip()
    if requested_date:
        try:
            captured = datetime.strptime(requested_date, '%Y-%m-%d')
            if captured.strftime('%Y-%m-%d') != requested_date:
                raise ValueError('Date must be YYYY-MM-DD')
        except ValueError:
            return jsonify({'status':'error','message':'Invalid date'}),400
    else:
        captured = None

    db = SessionLocal()
    try:
        if db.query(CaptureDraft).filter_by(userID=g.user_id, status='pending').count() >= 200:
            return jsonify({'status':'error','message':'Draft inbox limit reached'}),429
    finally:
        db.close()

    name = uuid.uuid4().hex + '-' + original
    target = _draft_folder() / name
    partial = _draft_folder() / (name + '.part')
    total = 0
    try:
        with partial.open('xb') as handle:
            os.fchmod(handle.fileno(), 0o600)
            while True:
                chunk = file.stream.read(1024*1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    return jsonify({'status':'error','message':'File exceeds 512 MiB'}),413
                handle.write(chunk)
        if total == 0:
            return jsonify({'status':'error','message':'Empty file'}),400
        os.replace(partial, target)
        kind = 'image' if extension in IMAGES else 'video-mov' if extension == 'mov' else 'video'
        db = SessionLocal()
        try:
            draft = CaptureDraft(
                userID=g.user_id, title=title, description=description,
                originalFilename=original, filename=name,
                mediaType=kind, capturedDate=captured, status='pending',
            )
            db.add(draft)
            db.commit()
            return jsonify({'status':'success','data':{'id':draft.id,'status':'pending'}}),201
        except Exception:
            db.rollback()
            target.unlink(missing_ok=True)
            raise
        finally:
            db.close()
    finally:
        partial.unlink(missing_ok=True)


@capture_bp.route('/api/v2/capture/drafts/<int:draft_id>/media')
@jwt_required
def capture_draft_media(draft_id):
    db = SessionLocal()
    try:
        draft = db.query(CaptureDraft).filter_by(
            id=draft_id, userID=g.user_id, status='pending'
        ).first()
        if not draft:
            abort(404)
        path = _draft_folder() / draft.filename
        if not path.is_file():
            abort(404)
        result = send_file(path, download_name=draft.originalFilename, conditional=True)
        result.headers['Cache-Control'] = 'private, no-store'
        return result
    finally:
        db.close()


@capture_bp.route('/api/v2/capture/drafts/<int:draft_id>/publish', methods=['POST'])
@jwt_required
def publish_capture_draft(draft_id):
    if not _csrf() or not has_list_permission('Create','Home'):
        abort(403)
    db = SessionLocal()
    moved = None
    try:
        draft = db.query(CaptureDraft).filter_by(id=draft_id, userID=g.user_id).first()
        if not draft:
            abort(404)
        if draft.status == 'published':
            return jsonify({'status':'success','data':{'id':draft.publishedItemID,'already_published':True}})
        if draft.status != 'pending':
            return jsonify({'status':'error','message':'Draft needs manual reconciliation'}),409
        source = _draft_folder() / draft.filename
        if not source.is_file():
            return jsonify({'status':'error','message':'Draft media missing'}),409
        # Lock the draft state before publication. An interrupted operation is
        # never blindly retried to create a duplicate.
        draft.status = 'publishing'
        db.commit()
        from app.routes.api import _get_upload_folder
        extension = Path(draft.filename).suffix.lower().lstrip('.')
        folder = Path(_get_upload_folder(extension))
        folder.mkdir(parents=True, exist_ok=True)
        moved = folder / draft.filename
        os.replace(source, moved)
        item = Item(
            title=draft.title, content=draft.description,
            contentType=draft.mediaType, listType=1, contentURL=draft.filename,
            createdByUser=g.user_id, edition=get_setting_by_name('sm_edition').value,
            dateCreated=draft.capturedDate or datetime.utcnow(),
        )
        db.add(item)
        db.flush()
        draft.status = 'published'
        draft.publishedItemID = item.id
        db.commit()
        return jsonify({'status':'success','data':{'id':item.id}})
    except Exception:
        db.rollback()
        # The draft remains marked "publishing" after an ambiguous failure;
        # its original is recovered privately when safe to do so.
        if moved and moved.exists() and draft is not None:
            original = _draft_folder() / draft.filename
            if not original.exists():
                os.replace(moved, original)
        raise
    finally:
        db.close()


@capture_bp.route('/api/v2/capture/drafts/<int:draft_id>', methods=['DELETE'])
@jwt_required
def delete_capture_draft(draft_id):
    if not _csrf():
        abort(403)
    db = SessionLocal()
    try:
        draft = db.query(CaptureDraft).filter_by(id=draft_id, userID=g.user_id).first()
        if not draft:
            abort(404)
        if draft.status != 'pending':
            return jsonify({'status':'error','message':'Only unpublished drafts can be removed'}),409
        (_draft_folder() / draft.filename).unlink(missing_ok=True)
        db.delete(draft)
        db.commit()
        return jsonify({'status':'success'})
    finally:
        db.close()


@capture_bp.route('/api/v2/capture/drafts/<int:draft_id>', methods=['PATCH'])
@jwt_required
def edit_capture_draft(draft_id):
    if not _csrf() or not request.is_json:
        abort(403)
    payload = request.get_json(silent=True) or {}
    title = payload.get('title')
    description = payload.get('description')
    if (not isinstance(title, str) or not 1 <= len(title.strip()) <= 255
            or not isinstance(description, str) or len(description) > 4000):
        return jsonify({'status':'error','message':'Invalid draft text'}),400
    db = SessionLocal()
    try:
        draft = db.query(CaptureDraft).filter_by(
            id=draft_id, userID=g.user_id, status='pending'
        ).first()
        if not draft:
            abort(404)
        draft.title = title.strip()
        draft.description = description.strip()
        db.commit()
    finally:
        db.close()
    return jsonify({'status':'success'})
