// Admin-only AI settings. Never send saved credentials to the browser.
async function loadAiSettings() {
    if (!document.getElementById('ai-settings-panel')) return;
    const response = await fetch('/api/v2/ai/config', { cache: 'no-store' });
    if (!response.ok) return;
    const config = (await response.json()).data;
    document.getElementById('ai-provider').value = config.provider || 'environment';
    document.getElementById('ai-base-url').value = config.base_url || '';
    document.getElementById('ai-model').value = config.model || '';
    document.getElementById('ai-system-prompt').value = config.system_prompt || '';
    document.getElementById('ai-api-key').value = '';
    document.getElementById('ai-api-key').placeholder = config.key_configured
        ? _('Credential stored securely. Leave blank to keep it.')
        : _('Enter API key, or leave blank for Ollama');
}

async function saveAiSettings() {
    const payload = {
        provider: document.getElementById('ai-provider').value,
        base_url: document.getElementById('ai-base-url').value,
        model: document.getElementById('ai-model').value,
        system_prompt: document.getElementById('ai-system-prompt').value,
        api_key: document.getElementById('ai-api-key').value,
    };
    const status = document.getElementById('ai-settings-status');
    try {
        const response = await fetch('/api/v2/ai/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': aiSettingsCsrf },
            body: JSON.stringify(payload),
        });
        const result = await response.json();
        status.textContent = result.message || (response.ok ? _('AI settings saved') : _('AI settings could not be saved'));
        if (response.ok) await loadAiSettings();
    } catch (_) {
        status.textContent = _('AI settings could not be saved');
        document.getElementById('ai-api-key').value = '';
    }
}

document.addEventListener('DOMContentLoaded', loadAiSettings);
