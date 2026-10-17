const memoryReactionKinds = [
    ['heart', 'favorite', 'Love'], ['like', 'thumb_up', 'Like'],
    ['laugh', 'sentiment_very_satisfied', 'Funny'], ['celebrate', 'celebration', 'Celebrate']
];

async function memoryRequest(url, method, data) {
    const opts = {credentials:'same-origin', method};
    if (method !== 'GET') {
        opts.headers = {'Content-Type':'application/json','X-CSRF-Token':window.memorySocialCsrf};
        opts.body = JSON.stringify(data || {});
    }
    const res = await fetch(url, opts);
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.message || 'Memory request failed');
    return json.data || {};
}

function memoryStatus(itemId, message) {
    const node = document.getElementById('memory-comment-status-' + itemId);
    if (node) node.textContent = message;
}

function memoryLabel(text) {
    return typeof _ === 'function' ? _(text) : text;
}

function memoryDate(value) {
    if (!value) return '';
    // Stored timestamps are UTC without an offset.
    const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z');
    if (isNaN(date)) return '';
    return date.toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'});
}

async function toggleMemoryDiscussion(itemId) {
    const panel = document.getElementById('memory-discussion-' + itemId);
    if (!panel) return;
    panel.hidden = !panel.hidden;
    document.getElementById('memory-discussion-toggle-' + itemId)
        ?.setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) await renderMemoryDiscussion(itemId);
}

async function renderMemoryDiscussion(itemId) {
    let data;
    try {
        data = await memoryRequest('/api/v2/memories/' + itemId + '/engagement', 'GET');
    } catch (error) {
        memoryStatus(itemId, error.message);
        return;
    }
    const reactions = document.getElementById('memory-reactions-' + itemId);
    const comments = document.getElementById('memory-comments-' + itemId);
    reactions.replaceChildren();
    comments.replaceChildren();
    for (const [kind, icon, label] of memoryReactionKinds) {
        const active = (data.mine || []).includes(kind);
        const total = (data.reactions || {})[kind] || 0;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'chip small round ' + (active ? 'primary' : 'border');
        button.title = memoryLabel(label);
        button.setAttribute('aria-label', memoryLabel(label) + ': ' + total);
        button.setAttribute('aria-pressed', String(active));
        const symbol = document.createElement('i');
        symbol.textContent = icon;
        if (active) symbol.classList.add('fill');
        button.append(symbol);
        if (total) {
            const count = document.createElement('span');
            count.textContent = total;
            button.append(count);
        }
        button.onclick = async () => {
            try {
                await memoryRequest('/api/v2/memories/' + itemId + '/reactions/' + kind,
                                    'PUT', {active: !active});
                await renderMemoryDiscussion(itemId);
            } catch (error) { memoryStatus(itemId, error.message); }
        };
        reactions.append(button);
    }
    const list = data.comments || [];
    const toggleLabel = document.querySelector('#memory-discussion-toggle-' + itemId + ' span');
    if (toggleLabel) {
        toggleLabel.textContent = memoryLabel('Comments') + (list.length ? ' (' + list.length + ')' : '');
    }
    for (const comment of list) {
        const article = document.createElement('div');
        article.className = 'memory-comment';
        const meta = document.createElement('div');
        meta.className = 'memory-comment-meta';
        const author = document.createElement('strong');
        author.textContent = comment.author || memoryLabel('Family member');
        const when = document.createElement('small');
        when.textContent = memoryDate(comment.created);
        meta.append(author, when);
        if (comment.can_delete) {
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'circle transparent small';
            remove.title = memoryLabel('Delete');
            remove.setAttribute('aria-label', memoryLabel('Delete'));
            const removeIcon = document.createElement('i');
            removeIcon.textContent = 'delete';
            remove.append(removeIcon);
            remove.onclick = async () => {
                if (!confirm(memoryLabel('Delete this comment?'))) return;
                try {
                    await memoryRequest('/api/v2/memories/comments/' + comment.id, 'DELETE');
                    await renderMemoryDiscussion(itemId);
                } catch (error) { memoryStatus(itemId, error.message); }
            };
            meta.append(remove);
        }
        const text = document.createElement('p');
        text.textContent = comment.content;
        article.append(meta, text);
        comments.append(article);
    }
}

async function postMemoryComment(itemId) {
    const field = document.getElementById('memory-comment-input-' + itemId);
    const content = (field?.value || '').trim();
    if (!content) return memoryStatus(itemId, memoryLabel('Write a comment first'));
    try {
        await memoryRequest('/api/v2/memories/' + itemId + '/comments', 'POST', {content});
        field.value = '';
        memoryStatus(itemId, '');
        await renderMemoryDiscussion(itemId);
    } catch (error) {
        memoryStatus(itemId, error.message);
    }
}

// Ctrl/Cmd+Enter posts a comment; plain Enter keeps adding lines.
document.addEventListener('keydown', event => {
    const field = event.target;
    if (event.key !== 'Enter' || !(event.metaKey || event.ctrlKey)) return;
    if (!field.id || !field.id.startsWith('memory-comment-input-')) return;
    event.preventDefault();
    postMemoryComment(field.id.replace('memory-comment-input-', ''));
});
