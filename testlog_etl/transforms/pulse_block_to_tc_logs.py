# encoding: utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Author: Kyle Lahnakoski (kyle@lahnakoski.com)
#
from __future__ import unicode_literals
from __future__ import division

import taskcluster

from pyLibrary import convert
from pyLibrary.debugs.logs import Log
from pyLibrary.dot import wrap

DEBUG = True


def process(source_key, source, destination, resources, please_stop=None):
    lines = source.read_lines()

    for i, line in enumerate(lines):
        tc_message = convert.json2value(line)
        taskid = tc_message.status.taskId
        Log.note("{{id}} found", id =taskid)

        try:
            # get the artifact list for the taskId
            tc_queue = taskcluster.Queue()
            artifacts = wrap(tc_queue.listLatestArtifacts(taskid))
            task = wrap(tc_queue.task(taskid))

            Log.note("{{task}}", task=task)
            Log.note(
                "Logs:\n{{logs}}",
                logs=[
                    {"name": a.name, "url": tc_queue.buildUrl('getLatestArtifact', taskid, a.name)}
                    for a in artifacts.artifacts
                ]
            )

        except Exception, e:
            Log.warning("problem", cause=e)


