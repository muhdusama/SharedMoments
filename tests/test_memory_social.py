"""Family discussion permissions and opt-in alerts using synthetic accounts and content."""
from datetime import datetime
import pytest
from app.db_queries import create_item, delete_item, update_user_setting
from app.models import MemoryComment, MemoryReaction, SessionLocal


@pytest.fixture
def social_memories(app):
    ids=[
        create_item('Synthetic family story','No personal data','text',1,'',2,datetime(2026,1,1),edition='all'),
        create_item('Invisible other edition','Do not reveal','text',1,'',2,datetime(2026,1,2),edition='friends')
    ]
    yield ids
    for id_ in ids:
        delete_item(id_)
    update_user_setting(2,'notification_engagement_enabled','False')


def _csrf(client):
    assert client.get('/home').status_code == 200
    with client.session_transaction() as state:
        return {'X-CSRF-Token': state['memory_social_csrf']}


def test_auth_and_edition_enforcement(client, child_client, social_memories):
    visible, hidden=social_memories
    assert client.get(f'/api/v2/memories/{visible}/engagement').status_code==302
    assert child_client.get(f'/api/v2/memories/{visible}/engagement').status_code==200
    assert child_client.get(f'/api/v2/memories/{hidden}/engagement').status_code==404
    assert child_client.get(f'/api/v2/memories/{visible}/engagement').json['data']['comments']==[]


def test_comments_require_csrf_are_displayed_and_owned(admin_client, child_client, social_memories):
    visible,hidden=social_memories
    token=_csrf(child_client)
    assert child_client.post(f'/api/v2/memories/{visible}/comments',json={'content':'Synthetic'}).status_code==403
    assert child_client.post(f'/api/v2/memories/{hidden}/comments',
                             json={'content':'No'},headers=token).status_code==404
    assert child_client.post(f'/api/v2/memories/{visible}/comments',
                             json={'content':''},headers=token).status_code==400
    result=child_client.post(f'/api/v2/memories/{visible}/comments',
                             json={'content':'<script>alert(1)</script>'},headers=token)
    assert result.status_code==201
    cid=result.json['data']['id']
    listed=admin_client.get(f'/api/v2/memories/{visible}/engagement')
    assert listed.status_code==200
    assert listed.json['data']['comments'][0]['content']=='<script>alert(1)</script>'
    assert listed.json['data']['comments'][0]['mine'] is False
    # Comment bodies are inserted in the DOM with textContent, not innerHTML.
    assert 'text.textContent = comment.content' in open('app/static/js/memory-social.js').read()
    assert child_client.patch(f'/api/v2/memories/comments/{cid}',
                              json={'content':'Edited synthetic'},headers=token).status_code==200
    assert admin_client.patch(f'/api/v2/memories/comments/{cid}',
                              json={'content':'Not my comment'},headers=_csrf(admin_client)).status_code==403
    assert admin_client.delete(f'/api/v2/memories/comments/{cid}',
                               json={},headers=_csrf(admin_client)).status_code==200
    assert admin_client.get(f'/api/v2/memories/{visible}/engagement').json['data']['comments']==[]


def test_reactions_are_idempotent_and_restricted(child_client, social_memories):
    visible,hidden=social_memories
    header=_csrf(child_client)
    path=f'/api/v2/memories/{visible}/reactions/heart'
    assert child_client.put(path,json={'active':True}).status_code==403
    assert child_client.put(path,json={'active':True},headers=header).status_code==200
    assert child_client.put(path,json={'active':True},headers=header).status_code==200
    assert child_client.get(f'/api/v2/memories/{visible}/engagement').json['data']['reactions']['heart']==1
    assert child_client.put(f'/api/v2/memories/{visible}/reactions/custom',
                            json={'active':True},headers=header).status_code==400
    assert child_client.put(f'/api/v2/memories/{hidden}/reactions/heart',
                            json={'active':True},headers=header).status_code==404
    assert child_client.put(path,json={'active':False},headers=header).status_code==200
    assert child_client.get(f'/api/v2/memories/{visible}/engagement').json['data']['reactions']['heart']==0


def test_notifications_require_opt_in_and_do_not_send_memory_content(
        child_client, admin_client, social_memories, monkeypatch):
    visible,_=social_memories
    header=_csrf(child_client)
    calls=[]
    monkeypatch.setattr('app.routes.memory_social.send_notification',
                        lambda recipient,title,body: calls.append((recipient,title,body)))
    assert child_client.post(f'/api/v2/memories/{visible}/comments',
                             json={'content':'Synthetic only'},headers=header).status_code==201
    assert calls==[]
    update_user_setting(2,'notification_engagement_enabled','True')
    assert child_client.post(f'/api/v2/memories/{visible}/comments',
                             json={'content':'Do not include these words in alerts'},headers=header).status_code==201
    assert len(calls)==1 and calls[0][0]==2
    assert 'Do not include' not in str(calls)
    assert child_client.put(f'/api/v2/memories/{visible}/reactions/heart',
                            json={'active':True},headers=header).status_code==200
    assert len(calls)==2
    assert child_client.put(f'/api/v2/memories/{visible}/reactions/heart',
                            json={'active':False},headers=header).status_code==200
    assert child_client.put(f'/api/v2/memories/{visible}/reactions/heart',
                            json={'active':True},headers=header).status_code==200
    # Removing and re-adding a reaction should not notify again on the same day.
    assert len(calls)==2
    # Idempotent re-application is not a second notification.
    assert child_client.put(f'/api/v2/memories/{visible}/reactions/heart',
                            json={'active':True},headers=header).status_code==200
    assert len(calls)==2


def test_social_metadata_removed_when_memory_deleted(admin_client, social_memories):
    visible,_=social_memories
    token=_csrf(admin_client)
    admin_client.post(f'/api/v2/memories/{visible}/comments',
                      json={'content':'Synthetic'},headers=token)
    admin_client.put(f'/api/v2/memories/{visible}/reactions/like',
                     json={'active':True},headers=token)
    delete_item(visible)
    db=SessionLocal()
    try:
        assert db.query(MemoryComment).filter_by(itemID=visible).count()==0
        assert db.query(MemoryReaction).filter_by(itemID=visible).count()==0
    finally:
        db.close()
