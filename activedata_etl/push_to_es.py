# encoding: utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Author: Kyle Lahnakoski (kyle@lahnakoski.com)
#
from __future__ import division
from __future__ import unicode_literals

from collections import Mapping

from pyLibrary import queries, aws
from pyLibrary.aws import s3
from pyLibrary.debugs import startup, constants
from pyLibrary.debugs.exceptions import Explanation, WarnOnException
from pyLibrary.debugs.logs import Log
from pyLibrary.dot import coalesce, unwrap, Dict, wrap
from pyLibrary.env import elasticsearch
from pyLibrary.maths import Math
from pyLibrary.maths.randoms import Random
from pyLibrary.thread.threads import Thread, Signal, Queue
from pyLibrary.times.timer import Timer
from activedata_etl.etl import parse_id_argument
from activedata_etl.sinks.multi_day_index import MultiDayIndex

split = {}


def splitter(work_queue, please_stop):
    for pair in iter(work_queue.pop_message, ""):
        if please_stop:
            for k,v in split.items():
                v.add(Thread.STOP)
            return
        if pair == None:
            continue

        message, payload = pair
        if not isinstance(payload, Mapping):
            Log.error("Not expecting a non-Mapping payload")

        key = payload.key
        with Explanation("Indexing records from {{bucket}}", bucket=payload.bucket):
            params = split.get(payload.bucket)
            if not params:
                message.delete()
                continue

        es = params.es
        bucket = params.bucket
        settings = params.settings

        extend_time = Timer("insert", silent=True)

        with extend_time:
            if settings.skip and Random.float() < settings.skip:
                Log.note("Skipping {{key}} from bucket {{bucket}}", key=key, bucket=bucket.name)
                work_queue.add(payload)
                message.delete()
                continue

            if settings.sample_only:
                sample_filter = {"terms": {"build.branch": settings.sample_only}}
            elif settings.sample_size:
                sample_filter = True
            else:
                sample_filter = None

            Log.note("Indexing {{key}} from bucket {{bucket}}", key=key, bucket=bucket.name)
            more_keys = bucket.keys(prefix=key)
            if not more_keys:
                Log.warning("No keys found {{message|json}}", message=payload)
            else:
                num_keys = es.copy(more_keys, bucket, sample_filter, settings.sample_size)

            add_message_to_queue(es.queue, payload.key, message)

        if num_keys > 1:
            Log.note(
                "Added {{num}} keys from {{key}} in {{bucket}} to {{es}} in {{duration}} ({{rate|round(places=3)}} keys/second)",
                num=num_keys,
                key=key,
                bucket=bucket.name,
                es=es.settings.index,
                duration=extend_time.duration,
                rate=num_keys / Math.max(extend_time.duration.seconds, 0.01)
            )


def safe_splitter(work_queue, please_stop):
    while not please_stop:
        try:
            with WarnOnException("Indexing records"):
                splitter(work_queue, please_stop)
        except Exception, e:
            Log.warning("problem", cause=e)


def add_message_to_queue(queue, payload_key, message):
    def _delete():
        Log.note("confirming message for {{id}}", id=payload_key)
        message.delete()

    queue.add(_delete)


def main():
    try:
        settings = startup.read_settings(defs=[
            {
                "name": ["--id"],
                "help": "id to process (prefix is ok too) ",
                "type": str,
                "dest": "id",
                "required": False
            },
            {
                "name": ["--new", "--reset"],
                "help": "to make a new index (then exit immediately)",
                "type": str,
                "dest": "reset",
                "required": False
            }
        ])
        constants.set(settings.constants)
        Log.start(settings.debug)

        queries.config.default = {
            "type": "elasticsearch",
            "settings": settings.elasticsearch.copy()
        }

        if settings.args.reset:
            es_settings = wrap([w.elasticsearch for w in settings.workers if w.name == settings.args.reset])
            if not es_settings:
                Log.error("Can not find worker going by name {{name|quote}}", name=settings.args.reset)
            elif len(es_settings) > 1:
                Log.error("More than one worker going by name {{name|quote}}", name=settings.args.reset)
            else:
                es_settings = es_settings.last()

            cluster = elasticsearch.Cluster(es_settings)
            alias = coalesce(es_settings.alias, es_settings.index)
            index = cluster.get_prototype(alias)[0]
            if index:
                Log.error("Index {{index}} has prefix={{alias|quote}}, and has no alias.  Can not make another.", alias=alias, index=index)
            else:
                Log.alert("Creating index for alias={{alias}}", alias=alias)
                cluster.create_index(settings=es_settings)
                Log.alert("Done.  Exiting.")
                return

        if settings.args.id:
            main_work_queue = Queue("local work queue")
            main_work_queue.extend(parse_id_argument(settings.args.id))
        else:
            main_work_queue = aws.Queue(settings=settings.work_queue)
        Log.note("Listen to queue {{queue}}, and read off of {{s3}}", queue=settings.work_queue.name, s3=settings.workers.source.bucket)

        for w in settings.workers:
            split[w.source.bucket] = Dict(
                es=MultiDayIndex(w.elasticsearch, queue_size=coalesce(w.queue_size, 1000), batch_size=unwrap(w.batch_size)),
                bucket=s3.Bucket(w.source),
                settings=w
            )
            Log.note("Bucket {{bucket}} using {{index}}", bucket=w.source.bucket, index=split[w.source.bucket].es.es.url)

        please_stop = Signal()
        Thread.run("splitter", safe_splitter, main_work_queue, please_stop=please_stop)

        def monitor_progress(please_stop):
            while not please_stop:
                Log.note("Remaining: {{num}}", num=len(main_work_queue))
                Thread.sleep(seconds=10)

        Thread.run(name="monitor progress", target=monitor_progress, please_stop=please_stop)

        aws.capture_termination_signal(please_stop)
        Thread.wait_for_shutdown_signal(please_stop=please_stop, allow_exit=True)
        please_stop.go()
        Log.note("Shutdown started")
    except Exception, e:
        Log.error("Problem with etl", e)
    finally:
        Log.stop()


if __name__ == "__main__":
    main()