async function searchMutation(path, method, payload) {
    const response = await fetch(path, {
        method,
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': window.memorySearchCsrf},
        body: JSON.stringify(payload || {})
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || 'Request failed');
    return data;
}
function searchStatus(message) {
    const node = document.getElementById('memory-search-status');
    if (node) node.textContent = message;
}
async function saveSearch() {
    const name = prompt('Save search as (e.g. Holidays):');
    if (!name || !name.trim()) return;
    const params = new URLSearchParams(location.search);
    const fields = ['q','tag','author','date_from','date_to','media'];
    const filters = Object.fromEntries(fields.map(key => [key, params.get(key) || '']));
    try {
        await searchMutation('/api/v2/memories/saved-searches', 'POST', {name: name.trim(), filters});
        location.reload();
    } catch (e) { searchStatus(e.message); }
}
async function deleteSearch(id) {
    if (!confirm('Delete saved search?')) return;
    try {
        await searchMutation('/api/v2/memories/saved-searches/' + id, 'DELETE');
        location.reload();
    } catch (e) { searchStatus(e.message); }
}
async function editTags(id, tags) {
    const answer = prompt('Tags (lowercase, comma-separated):', tags.join(', '));
    if (answer === null) return;
    const values = answer.split(',').map(x => x.trim()).filter(Boolean);
    try {
        await searchMutation('/api/v2/memories/' + id + '/tags', 'PUT', {tags: values});
        location.reload();
    } catch (e) { searchStatus(e.message); }
}
