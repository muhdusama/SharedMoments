const memoryReactionKinds = [
    ['heart', 'favorite'], ['like', 'thumb_up'],
    ['laugh', 'sentiment_very_satisfied'], ['celebrate', 'celebration']
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

async function toggleMemoryDiscussion(itemId) {
    const panel = document.getElementById('memory-discussion-' + itemId);
    if (!panel) return;
    panel.hidden = !panel.hidden;
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
    for (const [kind, icon] of memoryReactionKinds) {
        const active = (data.mine || []).includes(kind);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'chip small ' + (active ? 'primary-container' : 'border');
        const symbol = document.createElement('i');
        symbol.textContent = icon;
        const count = document.createElement('span');
        count.textContent = kind + ' ' + ((data.reactions || {})[kind] || 0);
        button.append(symbol, count);
        button.setAttribute('aria-pressed', String(active));
        button.onclick = async () => {
            try {
                await memoryRequest('/api/v2/memories/' + itemId + '/reactions/' + kind,
                                    'PUT', {active: !active});
                await renderMemoryDiscussion(itemId);
            } catch (error) { memoryStatus(itemId, error.message); }
        };
        reactions.append(button);
    }
    for (const comment of (data.comments || [])) {
        const article = document.createElement('div');
        article.className = 'padding surface-container';
        const by = document.createElement('small');
        by.textContent = comment.author + ' · ' + (comment.created || '');
        const text = document.createElement('p');
        text.textContent = comment.content;
        text.style.whiteSpace = 'pre-wrap';
        article.append(by, text);
        if (comment.can_delete) {
            const remove = document.createElement('button');
            remove.className = 'small border';
            remove.textContent = 'Delete';
            remove.onclick = async () => {
                if (!confirm('Delete this comment?')) return;
                try {
                    await memoryRequest('/api/v2/memories/comments/' + comment.id, 'DELETE');
                    await renderMemoryDiscussion(itemId);
                } catch (error) { memoryStatus(itemId, error.message); }
            };
            article.append(remove);
        }
        comments.append(article);
    }
}

async function postMemoryComment(itemId) {
    const field = document.getElementById('memory-comment-input-' + itemId);
    const content = (field?.value || '').trim();
    if (!content) return memoryStatus(itemId, 'Write a comment first');
    try {
        await memoryRequest('/api/v2/memories/' + itemId + '/comments', 'POST', {content});
        field.value = '';
        await renderMemoryDiscussion(itemId);
        memoryStatus(itemId, 'Comment added');
    } catch (error) {
        memoryStatus(itemId, error.message);
    }
}
