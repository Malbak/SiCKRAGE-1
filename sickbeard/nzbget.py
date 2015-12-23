# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: https://sickrage.tv
# Git: https://github.com/SiCKRAGETV/SickRage.git
#
# This file is part of SickRage.
#
# SickRage is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickRage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickRage.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import datetime
import httplib
import logging
import xmlrpclib
from base64 import standard_b64encode

import sickbeard
from providers import GenericProvider
from sickbeard import helpers
from sickbeard.common import Quality


def sendNZB(nzb, proper=False):
    """
    Sends NZB to NZBGet client

    :param nzb: nzb object
    :param proper: True if this is a Proper download, False if not. Defaults to False
    """
    addToTop = False
    nzbgetprio = 0
    category = sickbeard.NZBGET_CATEGORY
    if nzb.show.is_anime:
        category = sickbeard.NZBGET_CATEGORY_ANIME

    if sickbeard.NZBGET_USE_HTTPS:
        nzbgetXMLrpc = "https://%(username)s:%(password)s@%(host)s/xmlrpc"
    else:
        nzbgetXMLrpc = "http://%(username)s:%(password)s@%(host)s/xmlrpc"

    if sickbeard.NZBGET_HOST == None:
        logging.error("No NZBget host found in configuration. Please configure it.")
        return False

    url = nzbgetXMLrpc % {"host": sickbeard.NZBGET_HOST, "username": sickbeard.NZBGET_USERNAME,
                          "password": sickbeard.NZBGET_PASSWORD}

    nzbGetRPC = xmlrpclib.ServerProxy(url)
    try:
        if nzbGetRPC.writelog("INFO", "SiCKRAGE connected to drop of %s any moment now." % (nzb.name + ".nzb")):
            logging.debug("Successful connected to NZBget")
        else:
            logging.error("Successful connected to NZBget, but unable to send a message")

    except httplib.socket.error:
        logging.error(
                "Please check your NZBget host and port (if it is running). NZBget is not responding to this combination")
        return False

    except xmlrpclib.ProtocolError as e:
        if e.errmsg == "Unauthorized":
            logging.error("NZBget username or password is incorrect.")
        else:
            logging.error("Protocol Error: " + e.errmsg)
        return False

    dupekey = ""
    dupescore = 0
    # if it aired recently make it high priority and generate DupeKey/Score
    for curEp in nzb.episodes:
        if dupekey == "":
            if curEp.show.indexer == 1:
                dupekey = "SiCKRAGE-" + str(curEp.show.indexerid)
            elif curEp.show.indexer == 2:
                dupekey = "SiCKRAGE-tvr" + str(curEp.show.indexerid)
        dupekey += "-" + str(curEp.season) + "." + str(curEp.episode)
        if datetime.date.today() - curEp.airdate <= datetime.timedelta(days=7):
            addToTop = True
            nzbgetprio = sickbeard.NZBGET_PRIORITY
        else:
            category = sickbeard.NZBGET_CATEGORY_BACKLOG
            if nzb.show.is_anime:
                category = sickbeard.NZBGET_CATEGORY_ANIME_BACKLOG

    if nzb.quality != Quality.UNKNOWN:
        dupescore = nzb.quality * 100
    if proper:
        dupescore += 10

    nzbcontent64 = None
    if nzb.resultType == "nzbdata":
        data = nzb.extraInfo[0]
        nzbcontent64 = standard_b64encode(data)

    logging.info("Sending NZB to NZBget")
    logging.debug("URL: " + url)

    try:
        # Find out if nzbget supports priority (Version 9.0+), old versions beginning with a 0.x will use the old command
        nzbget_version_str = nzbGetRPC.version()
        nzbget_version = helpers.tryInt(nzbget_version_str[:nzbget_version_str.find(".")])
        if nzbget_version == 0:
            if nzbcontent64 is not None:
                nzbget_result = nzbGetRPC.append(nzb.name + ".nzb", category, addToTop, nzbcontent64)
            else:
                if nzb.resultType == "nzb":
                    genProvider = GenericProvider("")
                    data = genProvider.getURL(nzb.url)
                    if data == None:
                        return False
                    nzbcontent64 = standard_b64encode(data)
                nzbget_result = nzbGetRPC.append(nzb.name + ".nzb", category, addToTop, nzbcontent64)
        elif nzbget_version == 12:
            if nzbcontent64 is not None:
                nzbget_result = nzbGetRPC.append(nzb.name + ".nzb", category, nzbgetprio, False,
                                                 nzbcontent64, False, dupekey, dupescore, "score")
            else:
                nzbget_result = nzbGetRPC.appendurl(nzb.name + ".nzb", category, nzbgetprio, False,
                                                    nzb.url, False, dupekey, dupescore, "score")
        # v13+ has a new combined append method that accepts both (url and content)
        # also the return value has changed from boolean to integer
        # (Positive number representing NZBID of the queue item. 0 and negative numbers represent error codes.)
        elif nzbget_version >= 13:
            nzbget_result = True if nzbGetRPC.append(nzb.name + ".nzb",
                                                     nzbcontent64 if nzbcontent64 is not None else nzb.url,
                                                     category, nzbgetprio, False, False, dupekey, dupescore,
                                                     "score") > 0 else False
        else:
            if nzbcontent64 is not None:
                nzbget_result = nzbGetRPC.append(nzb.name + ".nzb", category, nzbgetprio, False,
                                                 nzbcontent64)
            else:
                nzbget_result = nzbGetRPC.appendurl(nzb.name + ".nzb", category, nzbgetprio, False,
                                                    nzb.url)

        if nzbget_result:
            logging.debug("NZB sent to NZBget successfully")
            return True
        else:
            logging.error("NZBget could not add %s to the queue" % (nzb.name + ".nzb"))
            return False
    except Exception:
        logging.error("Connect Error to NZBget: could not add %s to the queue" % (nzb.name + ".nzb"))
        return False
