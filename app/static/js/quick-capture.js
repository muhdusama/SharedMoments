async function captureMutation(id, action, payload) {
    const path = '/api/v2/capture/drafts/' + id +
        (action === 'publish' ? '/publish' : '');
    const method = action === 'publish' ? 'POST' :
                   action === 'discard' ? 'DELETE' : 'PATCH';
    const response = await fetch(path, {
        method, credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-CSRF-Token':window.captureCsrf},
        body:JSON.stringify(payload || {})
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        document.getElementById('capture-status').textContent = result.message || 'Draft change failed';
        return;
    }
    location.reload();
}
function publishCapture(id) {
    if (!confirm('Publish this memory and its media to all members of the current edition?')) return;
    captureMutation(id, 'publish');
}
function removeCapture(id) {
    if (!confirm('Discard this private draft and remove its uploaded file?')) return;
    captureMutation(id, 'discard');
}
function editCapture(id, title, description) {
    const newTitle = prompt('Memory title', title);
    if (newTitle === null) return;
    const newDescription = prompt('Memory description', description);
    if (newDescription === null) return;
    captureMutation(id, 'edit', {title: newTitle, description: newDescription});
}
