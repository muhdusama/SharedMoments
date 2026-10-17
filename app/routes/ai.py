from flask import Blueprint, Response, request, stream_with_context, jsonify, g, session
from app.routes.auth import jwt_required
from app.ai import stream_ai_response
from app.translation import _
from app.permissions import require_permission
import hmac
import secrets

ai_bp = Blueprint('ai', __name__)

@ai_bp.route('/api/v2/ai/config', methods=['GET', 'PUT'])
@jwt_required
@require_permission('Update Setting')
def ai_configuration():
    from app.ai_settings import public_ai_config, save_ai_config
    if request.method == 'GET':
        session.setdefault('ai_settings_csrf', secrets.token_urlsafe(32))
        result = public_ai_config()
        result['csrf_token'] = session['ai_settings_csrf']
        response = jsonify({'status': 'success', 'data': result})
        response.headers['Cache-Control'] = 'no-store'
        return response

    actual = request.headers.get('X-CSRF-Token', '')
    expected = session.get('ai_settings_csrf', '')
    if (not request.is_json or not request.cookies.get('jwt_token')
            or not actual or not expected or not hmac.compare_digest(actual, expected)):
        return jsonify({'status': 'error', 'message': 'CSRF validation failed'}), 403
    try:
        save_ai_config(request.get_json())
    except ValueError as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 400
    return jsonify({'status': 'success', 'data': public_ai_config()})


@ai_bp.route('/api/v2/ai/enhance', methods=['POST'])
@jwt_required
def enhance_text():
    # Check if user has any Create or Update permission for any list
    user_perms = getattr(g, 'user_permissions', set())
    has_any = any(p.startswith('Create ') or p.startswith('Update ') for p in user_perms)
    if not has_any:
        return jsonify({
            'status': 'error',
            'message': _('Insufficient permissions'),
            'data': {'error_code': 403}
        }), 403

    text = request.form.get('text', '').strip()
    if not text:
        return Response("data: Error: No text provided\n\ndata: [DONE]\n\n",
                        mimetype='text/event-stream')

    return Response(
        stream_with_context(stream_ai_response(text)),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )
