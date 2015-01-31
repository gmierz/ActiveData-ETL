# encoding: utf-8
#
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Author: Kyle Lahnakoski (kyle@lahnakoski.com)
#


from __future__ import unicode_literals
from __future__ import division
from pyLibrary import convert

from pyLibrary import aws
from pyLibrary.aws.s3 import Bucket
from pyLibrary.debugs import startup
from pyLibrary.debugs.logs import Log

from pyLibrary.queries import Q
from pyLibrary.times.timer import Timer


def list_queue(settings, num):
    queue = aws.Queue(settings)
    for i in range(num):
        content = queue.pop()
        Log.note("{{content}}", {"content":content})
    queue.rollback()


def main():
    try:
        settings = startup.read_settings(defs={
            "name": ["--num"],
            "help": "number to show",
            "type": int,
            "dest": "num",
            "default": '10',
            "required": False
        })
        Log.start(settings.debug)
        list_queue(settings.source, settings.args.num)
    except Exception, e:
        Log.error("Problem with etl", e)
    finally:
        Log.stop()


if __name__ == "__main__":
    main()