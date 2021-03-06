# encoding: utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Author: Kyle Lahnakoski (kyle@lahnakoski.com)
#
from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

import os

import flask
from flask import Flask, Response

from mo_dots import listwrap, coalesce, unwraplist
from mo_json import value2json, json2value
from mo_logs import Log, constants, startup
from mo_logs.strings import utf82unicode, unicode2utf8
from mo_threads import Thread
from mo_times import Timer
from pyLibrary.env.flask_wrappers import cors_wrapper
from tuid.service import TUIDService
from tuid.util import map_to_array

OVERVIEW = None


class TUIDApp(Flask):

    def run(self, *args, **kwargs):
        # ENSURE THE LOGGING IS CLEANED UP
        try:
            Thread.run("tuid daemon", service._daemon)
            Flask.run(self, *args, **kwargs)
        except BaseException as e:  # MUST CATCH BaseException BECAUSE argparse LIKES TO EXIT THAT WAY, AND gunicorn WILL NOT REPORT
            Log.warning("TUID service shutdown!", cause=e)
        finally:
            Log.stop()


flask_app = None
config = None
service = None


@cors_wrapper
def tuid_endpoint(path):
    try:
        request_body = flask.request.get_data().strip()
        query = json2value(utf82unicode(request_body))

        # ENSURE THE QUERY HAS THE CORRECT FORM
        if query['from'] != 'files':
            Log.error("Can only handle queries on the `files` table")

        ands = listwrap(query.where['and'])
        if len(ands) != 2:
            Log.error(
                'expecting a simple where clause with following structure\n{{example|json}}',
                example={"and": [
                    {"eq": {"revision": "<REVISION>"}},
                    {"in": {"path": ["<path1>", "<path2>", "...", "<pathN>"]}}
                ]}
            )

        rev = None
        paths = None
        for a in ands:
            rev = coalesce(rev, a.eq.revision)
            paths = unwraplist(coalesce(paths, a['in'].path, a.eq.path))

        paths = listwrap(paths)
        if len(paths) <= 0:
            Log.warning("Can't find file paths found in request: {{request}}", request=request_body)
            response = [("Error in app.py - no paths found", [])]
        else:
            # RETURN TUIDS
            with Timer("tuid internal response time for {{num}} files", {"num": len(paths)}):
                response = service.get_tuids_from_files(revision=rev, files=paths, going_forward=True)

        if query.meta.format == 'list':
            formatter = _stream_list
        else:
            formatter = _stream_table

        return Response(
            formatter(response),
            status=200,
            headers={
                "Content-Type": "application/json"
            }
        )
    except Exception as e:
        Log.warning("could not handle request", cause=e)
        return Response(
            unicode2utf8(value2json(e, pretty=True)),
            status=400,
            headers={
                "Content-Type": "text/html"
            }
        )


def _stream_table(files):
    yield b'{"format":"table", "header":["path", "tuids"], "data":['
    for f, pairs in files:
        yield value2json([f, map_to_array(pairs)]).encode('utf8')
    yield b']}'


def _stream_list(files):
    sep = b'{"format":"list", "data":['
    for f, pairs in files:
        yield sep
        yield value2json({"path": f, "tuids": map_to_array(pairs)}).encode('utf8')
        sep = b","
    yield b']}'


@cors_wrapper
def _head(path):
    return Response(b'', status=200)


@cors_wrapper
def _default(path):
    return Response(
        OVERVIEW,
        status=200,
        headers={
            "Content-Type": "text/html"
        }
    )


if __name__ in ("__main__",):
    flask_app = TUIDApp(__name__)

    flask_app.add_url_rule(str('/'), None, tuid_endpoint, defaults={'path': ''}, methods=[str('GET'), str('POST')])
    flask_app.add_url_rule(str('/<path:path>'), None, tuid_endpoint, methods=[str('GET'), str('POST')])

    try:
        config = startup.read_settings(
            filename=os.environ.get('TUID_CONFIG')
        )
        constants.set(config.constants)
        Log.start(config.debug)

        service = TUIDService(config.tuid)

        # Run the daemon
        #daemon = Thread.run("TUID Daemon", service._daemon)
    except BaseException as e:  # MUST CATCH BaseException BECAUSE argparse LIKES TO EXIT THAT WAY, AND gunicorn WILL NOT REPORT
        try:
            Log.error("Serious problem with TUID service construction!  Shutdown!", cause=e)
        finally:
            Log.stop()

    if config.flask:
        if config.flask.port and config.args.process_num:
            config.flask.port += config.args.process_num

        flask_app.run(**config.flask)


