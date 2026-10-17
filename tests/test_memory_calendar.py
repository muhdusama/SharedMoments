"""Calendar navigation and access tests using synthetic posts only."""

from datetime import datetime

import pytest


@pytest.fixture
def sample_calendar_posts(app):
    from app.db_queries import create_item, delete_item
    from app.models import SessionLocal, Setting

    db = SessionLocal()
    edition = db.query(Setting).filter_by(name='sm_edition').one()
    original_edition = edition.value
    edition.value = 'family'
    db.commit()
    db.close()

    ids = []
    try:
        ids.append(create_item('Saturday walk', 'A synthetic family memory',
                               'text', 1, '', 2, datetime(2026, 10, 17, 9, 15), edition='family'))
        ids.append(create_item('Saturday photos', 'Another synthetic entry',
                               'galleryStartWithImage', 1, 'demo.jpg;second.jpg', 3,
                               datetime(2026, 10, 17, 17, 0), edition='all'))
        ids.append(create_item('November activity', 'A different month',
                               'text', 1, '', 2, datetime(2026, 11, 1), edition='family'))
        ids.append(create_item('Other-edition post', 'Should not be shown',
                               'text', 1, '', 2, datetime(2026, 10, 17), edition='couples'))
        yield ids
    finally:
        for item_id in ids:
            delete_item(item_id)
        db = SessionLocal()
        db.query(Setting).filter_by(name='sm_edition').one().value = original_edition
        db.commit()
        db.close()


def test_calendar_requires_sign_in(client):
    response = client.get('/calendar')
    assert response.status_code == 302
    assert '/login' in response.location


def test_calendar_requires_view_home(adult_client, monkeypatch):
    monkeypatch.setattr('app.routes.pages.has_list_permission', lambda action, name: False)
    assert adult_client.get('/calendar').status_code == 403


def test_calendar_marks_dates_and_shows_every_selected_post(child_client, sample_calendar_posts):
    first, second, other_month, other_edition = sample_calendar_posts

    month = child_client.get('/calendar?month=2026-10')
    assert month.status_code == 200
    assert b'October 2026' in month.data
    assert b'/calendar?month=2026-09' in month.data
    assert b'/calendar?month=2026-11' in month.data
    assert b'/calendar?date=2026-10-17#day-posts' in month.data
    assert b'2 posts' in month.data
    assert b'Saturday walk' not in month.data  # No posts displayed until a day is chosen.

    day = child_client.get('/calendar?date=2026-10-17')
    assert day.status_code == 200
    assert b'Saturday walk' in day.data
    assert b'Saturday photos' in day.data
    assert b'A synthetic family memory' in day.data
    assert b'Other-edition post' not in day.data
    assert b'November activity' not in day.data
    assert f'/home#article_{first}'.encode() in day.data
    assert f'/home#article_{second}'.encode() in day.data
    assert f'/gallery/{second}'.encode() in day.data

    november = child_client.get('/calendar?date=2026-11-01')
    assert november.status_code == 200
    assert b'November activity' in november.data
    assert b'Saturday walk' not in november.data


def test_date_without_posts_displays_empty_message(adult_client, sample_calendar_posts):
    response = adult_client.get('/calendar?date=2026-10-18')
    assert response.status_code == 200
    assert b'No posts on this date.' in response.data


@pytest.mark.parametrize('query', [
    'month=bad', 'month=2026-13', 'month=2026-2', 'month=0000-01',
    'date=not-a-date', 'date=2026-02-30', 'date=2026-W42-6',
])
def test_invalid_dates_return_bad_request(adult_client, query):
    assert adult_client.get(f'/calendar?{query}').status_code == 400


def test_year_boundaries_do_not_break_calendar(adult_client):
    earliest = adult_client.get('/calendar?month=0001-01')
    assert earliest.status_code == 200
    assert b'Previous month' not in earliest.data
    assert b'/calendar?month=0001-02' in earliest.data

    latest = adult_client.get('/calendar?month=9999-12')
    assert latest.status_code == 200
    assert b'Next month' not in latest.data
    assert b'/calendar?month=9999-11' in latest.data


def test_week_starts_with_locale(adult_client):
    with adult_client.session_transaction() as stored:
        stored['lang'] = 'en-US'
    sunday = adult_client.get('/calendar?month=2026-10')
    assert sunday.status_code == 200
    assert b'<th scope="col">Sun</th>' in sunday.data

    with adult_client.session_transaction() as stored:
        stored['lang'] = 'de-DE'
    monday = adult_client.get('/calendar?month=2026-10')
    assert monday.status_code == 200
    assert b'<th scope="col">Mo.</th>' in monday.data
    assert b'Oktober 2026' in monday.data

    with adult_client.session_transaction() as stored:
        stored['lang'] = 'en-AU'
    australian = adult_client.get('/calendar?month=2026-10')
    assert australian.status_code == 200
    assert b'<th scope="col">Mon</th>' in australian.data


def test_calendar_post_text_is_escaped(child_client, app):
    from app.db_queries import create_item, delete_item
    item_id = create_item('<script>alert(1)</script>', '<img src=x onerror=alert(1)>',
                          'text', 1, '', 2, datetime(2026, 10, 17), edition='all')
    try:
        result = child_client.get('/calendar?date=2026-10-17')
        assert result.status_code == 200
        assert b'&lt;script&gt;' in result.data
        assert b'&lt;img src=x onerror=alert(1)&gt;' in result.data
        assert b'<script>alert(1)</script>' not in result.data
    finally:
        delete_item(item_id)
