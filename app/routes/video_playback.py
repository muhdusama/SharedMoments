"""Authenticated playback derivatives; sharing only through existing authorised links."""
from datetime import datetime

from flask import Blueprint, abort, send_file, session
from app.db_queries import get_share_by_token
from app.media_playback import browser_video_path
from app.routes.auth import jwt_required

video_bp = Blueprint('video_playback', __name__)


@video_bp.route('/api/v2/media/play/<filename>')
@jwt_required
def play_video(filename):
    response = send_file(browser_video_path(filename), mimetype='video/mp4', conditional=True)
    response.headers['Accept-Ranges'] = 'bytes'
    return response


@video_bp.route('/s/<token>/media/play/<filename>')
def shared_play_video(token, filename):
    share, item = get_share_by_token(token)
    if not share or not item:
        abort(404)
    if share.expiresAt and datetime.utcnow() > share.expiresAt:
        abort(410)
    if share.passwordHash and token not in session.get('verified_shares', []):
        abort(403)
    if filename not in (item.contentURL or '').split(';'):
        abort(404)
    response = send_file(browser_video_path(filename), mimetype='video/mp4', conditional=True)
    response.headers['Accept-Ranges'] = 'bytes'
    return response
