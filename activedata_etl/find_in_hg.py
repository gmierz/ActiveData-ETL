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

from mo_future import text_type
from mo_hg.hg_mozilla_org import HgMozillaOrg

hg = HgMozillaOrg()
hg.find_changeset("8f6cb5bed0cc")
