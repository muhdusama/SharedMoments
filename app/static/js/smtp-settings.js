// Administrator-only SMTP configuration. Never request or display saved passwords.
async function loadSmtpSettings() {
    const panel = document.getElementById('smtp-settings-panel');
    if (!panel) return;
    const response = await fetch('/api/v2/smtp/config', { cache: 'no-store' });
    if (!response.ok) return;
    const config = (await response.json()).data;
    document.getElementById('smtp-enabled').checked = !!config.enabled;
    document.getElementById('smtp-host').value = config.host || '';
    document.getElementById('smtp-port').value = config.port || 587;
    document.getElementById('smtp-security').value = config.security || 'starttls';
    document.getElementById('smtp-username').value = config.username || '';
    document.getElementById('smtp-from').value = config.sender || '';
    document.getElementById('smtp-password').value = '';
    document.getElementById('smtp-password').placeholder = config.secret_configured
        ? (config.source === 'environment'
            ? _('Enter password to switch from environment settings')
            : _('Password stored securely. Leave blank to keep it.'))
        : _('SMTP password');
}

async function smtpSettingsRequest(path, payload) {
    const response = await fetch(path, {
        method: path.endsWith('/test') ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': smtpSettingsCsrf },
        body: JSON.stringify(payload || {}),
    });
    const result = await response.json();
    document.getElementById('smtp-settings-status').textContent =
        result.message || (response.ok ? _('SMTP settings updated') : _('SMTP request failed'));
    if (!response.ok) throw new Error(result.message || 'SMTP request failed');
    return result;
}

async function saveSmtpSettings() {
    const data = {
        enabled: document.getElementById('smtp-enabled').checked,
        host: document.getElementById('smtp-host').value,
        port: Number(document.getElementById('smtp-port').value),
        security: document.getElementById('smtp-security').value,
        username: document.getElementById('smtp-username').value,
        password: document.getElementById('smtp-password').value,
        sender: document.getElementById('smtp-from').value,
    };
    try {
        await smtpSettingsRequest('/api/v2/smtp/config', data);
        await loadSmtpSettings();
    } catch (_) {
        document.getElementById('smtp-password').value = '';
    }
}

async function testSmtpDelivery() {
    try {
        await smtpSettingsRequest('/api/v2/smtp/test', {});
    } catch (_) {
        // Error message is already shown in the status area.
    }
}

document.addEventListener('DOMContentLoaded', loadSmtpSettings);
