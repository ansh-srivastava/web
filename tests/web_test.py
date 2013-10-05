import glob
import hashlib
import os
import os.path
import re
import shutil
import traceback

from flask import json

from libearth.compat import binary
from libearth.crawler import crawl
from libearth.feedlist import (Feed as FeedOutline,
                               FeedCategory as CategoryOutline, FeedList)
from libearth.schema import write

from earthreader.web import app

import httpretty
from pytest import yield_fixture


@app.errorhandler(400)
def bad_request_handler_for_testing(exception):
    '''Custom error handler of :http:statuscode:`400` for unit testing
    to know how it's going in the application.

    '''
    traceback.print_exc(exception)
    return (
        traceback.format_exc(exception),
        400,
        {'Content-Type': 'text/plain; charset=utf-8'}
    )


@app.errorhandler(500)
def server_error_handler_for_testing(exception):
    '''Custom error handler of :http:statuscode:`500` for unit testing
    to know how it's going in the application.

    '''
    traceback.print_exc(exception)
    return (
        traceback.format_exc(exception),
        500,
        {'Content-Type': 'text/plain; charset=utf-8'}
    )


app.config.update(dict(
    REPOSITORY='tests/repo/',
    OPML='test.opml'
))


REPOSITORY = app.config['REPOSITORY']
OPML = app.config['OPML']


opml = '''
<opml version="1.0">
  <head>
    <title>test opml</title>
  </head>
  <body>
    <outline text="categoryone" title="categoryone">
        <outline type="atom" text="Feed One" title="Feed One"
        xmlUrl="http://feedone.com/feed/atom/" />
        <outline text="categorytwo" title="categorytwo">
            <outline type="atom" text="Feed Two" title="Feed Two"
            xmlUrl="http://feedtwo.com/feed/atom/" />
        </outline>
    </outline>
    <outline type="atom" text="Feed Three" title="Feed Three"
    xmlUrl="http://feedthree.com/feed/atom/" />
    <outline text="categorythree" title="categorythree">
        <outline type="atom" text="Feed Four" title="Feed Four"
        xmlUrl="http://feedfour.com/feed/atom/" />
    </outline>
  </body>
</opml>
'''


feed_one= '''
<feed xmlns="http://www.w3.org/2005/Atom">
    <title type="text">Feed One</title>
    <id>http://feedone.com/feed/atom/</id>
    <updated>2013-08-19T07:49:20+07:00</updated>
    <link type="text/html" rel="alternate" href="http://feedone.com" />
</feed>
'''

feed_two= '''
<feed xmlns="http://www.w3.org/2005/Atom">
    <title type="text">Feed Two</title>
    <id>http://feedtwo.com/feed/atom/</id>
    <updated>2013-08-19T07:49:20+07:00</updated>
    <link type="text/html" rel="alternate" href="http://feedtwo.com" />
</feed>
'''


feed_three= '''
<feed xmlns="http://www.w3.org/2005/Atom">
    <title type="text">Feed Three</title>
    <id>http://feedthree.com/feed/atom/</id>
    <updated>2013-08-19T07:49:20+07:00</updated>
    <link type="text/html" rel="alternate" href="http://feedthree.com" />
</feed>
'''


feed_four = '''
<feed xmlns="http://www.w3.org/2005/Atom">
    <title type="text">Feed Four</title>
    <id>http://feedfour.com/feed/atom/</id>
    <updated>2013-08-19T07:49:20+07:00</updated>
    <link type="text/html" rel="alternate" href="http://feedfour.com" />
</feed>
'''


def get_feed_urls(category, urls=[]):
    for child in category:
        if isinstance(child, FeedOutline):
            urls.append(child.xml_url)
        elif isinstance(child, CategoryOutline):
            get_feed_urls(child, urls)
    return urls


@yield_fixture
def xmls():
    httpretty.enable()
    httpretty.register_uri(httpretty.GET, 'http://feedone.com/feed/atom/',
                          body=feed_one)
    httpretty.register_uri(httpretty.GET, 'http://feedtwo.com/feed/atom/',
                          body=feed_two)
    httpretty.register_uri(httpretty.GET, 'http://feedthree.com/feed/atom/',
                          body=feed_three)
    httpretty.register_uri(httpretty.GET, 'http://feedfour.com/feed/atom/',
                          body=feed_four)
    os.mkdir(REPOSITORY)
    feed_list = FeedList(opml, is_xml_string=True)
    feed_urls = get_feed_urls(feed_list)
    generator = crawl(feed_urls, 4)
    for result in generator:
        feed_data = result[1][0]
        feed_url = result[0]
        file_name = hashlib.sha1(binary(feed_url)).hexdigest() + '.xml'
        with open(REPOSITORY + file_name, 'w+') as f:
            for chunk in write(feed_data, indent='    ',
                               canonical_order=True):
                f.write(chunk)
    feed_list.save_file(REPOSITORY + OPML)
    yield
    shutil.rmtree(REPOSITORY)
    httpretty.disable()
    

def test_all_feeds(xmls):
    with app.test_client() as client:
        r = client.get('/feeds/')
        assert r.status_code == 200
        result = json.loads(r.data)
        feeds = result['feeds']
        assert feeds[0]['title'] == 'Feed Three'
        assert feeds[1]['title'] == 'categoryone'
        assert feeds[1]['feeds'][0]['title'] == 'Feed One'
        assert feeds[1]['feeds'][1]['title'] == 'categorytwo'
        assert feeds[1]['feeds'][1]['feeds'][0]['title'] == 'Feed Two'
        assert feeds[2]['title'] == 'categorythree'
        assert feeds[2]['feeds'][0]['title'] == 'Feed Four'


def test_feed_entries(xmls):
    RE_PATTERN = re.compile('(?:.?)+/feeds/(.+)/entries')
    with app.test_client() as client:
        r = client.get('/feeds/')
        assert r.status_code == 200
        result = json.loads(r.data)
        feeds = result['feeds']
        feed_url = feeds[0]['feed_url']
        r1 = client.get(feed_url)
        r1_data = json.loads(r1.data)
        assert r1.status_code == 200
        assert r1_data['title'] == 'Feed Three'
        feed_url = feeds[1]['feeds'][0]['feed_url']
        r1 = client.get(feed_url)
        assert r1.status_code == 200
        r1_data = json.loads(r1.data)
        match = RE_PATTERN.match(feed_url)
        feed_id = match.group(1)
        r2 = client.get('/feeds/' + feed_id + '/entries')
        assert r2.status_code == 200
        r2_data = json.loads(r2.data)
        assert r1_data['title'] == 'Feed One'
        assert r1_data == r2_data
        feed_url = feeds[1]['feeds'][1]['feeds'][0]['feed_url']
        r1 = client.get(feed_url)
        assert r1.status_code == 200
        r1_data = json.loads(r1.data)
        match = RE_PATTERN.match(feed_url)
        feed_id = match.group(1)
        r2 = client.get('/feeds/' + feed_id + '/entries')
        assert r2.status_code == 200
        r2_data = json.loads(r2.data)
        assert r1_data['title'] == 'Feed Two'
        assert r1_data == r2_data
        feed_url = feeds[2]['feeds'][0]['feed_url']
        r1 = client.get(feed_url)
        assert r1.status_code == 200
        r1_data = json.loads(r1.data)
        match = RE_PATTERN.match(feed_url)
        feed_id = match.group(1)
        r2 = client.get('/feeds/' + feed_id + '/entries')
        assert r2.status_code == 200
        r2_data = json.loads(r2.data)
        assert r1_data['title'] == 'Feed Four'
        assert r1_data == r2_data
