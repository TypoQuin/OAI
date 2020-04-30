#!/usr/bin/python3

# -----------------------------------------------------------
# Process latseq logs to get statistics and visualization
#
# (C) 2020 Flavien Ronteix--Jacquet, Lannion, France
# Released under MIT License
# email flavien.ronteixjacquet@orange.com
# -----------------------------------------------------------

"""Process latseq logs module

This modules is used to process latseq logs and provides
some useful statistics and stats

Example:
    ./latseq_logs.py -l /home/flavien/latseq.21042020.lseq

Attributes:
    none

TODO
    * categorize journeys in a path. For later filtering
    * find ALL in and out points (dynamically). Should I do ?
    * output a json more practical to use
    * APIify with flask to be called easily by the others modules
        https://programminghistorian.org/en/lessons/creating-apis-with-python-and-flask#creating-a-basic-flask-application
    * Rebuild_packet with multithreading because the algorithmc complexity is huge...

"""

import argparse
import re
import datetime
import operator
import statistics
import numpy
from copy import deepcopy
import pickle
# import math

#
# GLOBALS
#

# trick to reduce complexity
# Asumption : packet spend at maximum DEPTH_TO_SEARCH_PKT measure in the system
DEPTH_TO_SEARCH_PKT = 20
DEPTH_TO_SEARCH_FORKS = 10
# TODO : Too larg, I match between um and am

S_TO_MS = 1000
#
# UTILS
#


def epoch_to_datetime(epoch: float) -> str:
    """Convert an epoch to datetime"""
    return datetime.datetime.fromtimestamp(
        epoch).strftime('%Y%m%d_%H%M%S.%f')


def dstamp_to_epoch(dstamptime: str) -> float:
    """Convert a dstamptime to float epoch"""
    return float(datetime.datetime.strptime(
        dstamptime, "%Y%m%d_%H%M%S.%f"
    ).timestamp())


def path_to_str(pathP: list) -> str:
    """Use to get a string representing a path from a list"""
    if len(pathP) < 1:
        return ""
    if len(pathP) < 2:
        return pathP[0]
    res = f"{pathP[0]} -> "
    for i in range(1, len(pathP) - 1):
        res += f"{pathP[i]} -> "
    return res + f"{pathP[-1]}"

def dict_ids_to_str(idsP: dict) -> str:
    return '.'.join([f"{k}{v}" for k,v in idsP.items()])


def make_immutable_list(listP: list) -> tuple:
    return tuple(listP)


#
# STRUCTURES
#
class latseq_log:
    """class for log processing associated to a log file

    Args:
        logpathP (str): path to the log file

    Attributes:
        logpath (str): path to the log file
        initialized (bool): become true when __init__ is successfully done
        raw_inputs (:obj:`list` of :obj:`str`): list of lines from logpath file
        inputs (:obj:`list` of :obj:`str`): list of lines after a first pass
            of processing from raw_inputs
        dataids (:obj:`list` of :obj:`str`): list of dataids found in the logs
        points (:obj:`dict` of :obj:`list`): list of points
            points[i] (:obj:`dict`): a point
                points[i]['dir'] (:obj:`list` of int): list of direction where this point can be found
                points[i]['count'] (int): number of occurences of this point on `inputs`
                points[i]['next'] (:obj:`list` of str): list of possible next points
                points[i]['duration'] (:obj:`list` of float): list of duration for this point in the `journey`. WARNING: Computed at a rebuild journey function... not in build_points
        pointsInD (:obj:`list` of str): list of input points for Downlink
        pointsInU (:obj:`list` of str): list of input points for Uplink
        pointsOutD (:obj:`list` of str): list of output points for Downlink
        pointsOutU (:obj:`list` of str): list of output points for Uplink
        paths (:obj:`list` of :obj:`list`):
            list[0] is a list of all DownLink paths possibles
            list[1] is a list of all UpLink paths possibles
        timestamps (:obj:`list` of float): list of timestamps in the logs
        journeys (:obj:`dict`): the dictionnary containing journeys
            journeys[i] (:obj:`dict`): a journey
                journeys[i]['dir'] (int): 0 if a Downlink journey, 1 otherwise
                journeys[i]['glob'] (:obj:`dict`): the globals context ids to match necessary
                journeys[i]['completed'] (bool): True if the journey is compete, e.g. journey from an in to an out point
                journeys[i]['ts_in'] (float): timestamp at which the journey begins
                journeys[i]['ts_out'] (float): timestamp at which the journey ends if `completed`
                journeys[i]['next_points'] (:obj:`list`): the next points' identifier expected
                journeys[i]['set'] (:obj:`list`): list of measures in `input` corresponding to this journey
                journeys[i]['set_ids'] (:obj:`list`): the last measurement point identifier added
                journeys[i]['path'] (int): the path id according to self.paths
        out_journeys (:obj:`list`): the list of measurement point like `raw_inputs` but ordered, filtered and with unique identifier (uid) by journey
    """
    def __init__(self, logpathP: str):
        self.logpath = logpathP
        self.initialized = False
        # Open and Read the logpath file
        if not self.logpath:
            raise AssertionError("Error, no logpath provided")
        try:
            self.raw_inputs = list()
            self._read_log()
        except FileNotFoundError:
            raise FileNotFoundError(f"Error, {logpathP} not found")
        except IOError:
            raise IOError(f"Error at Reading {logpathP}")
        else:
            # Filter raw_inputs to fill inputs
            try:
                self.inputs = list()
                self.dataids = list()
                self._clean_log()
            except Exception:
                raise ValueError(f"Error in Cleaning or Filtering {logpathP}")
        # Build points
        try:
            self.points = dict()  # the couple (key, "next") is basically a graph
            self.pointsInD = ["ip", "rlc.tx.am"]
            self.pointsOutD = ["phy.out.proc"]
            self.pointsInU = ["phy.in.proc"]
            self.pointsOutU = ["ip"]
            self._build_points()
        except Exception:
            raise Exception("Error at getting points")
        else:
            # Build paths
            try:
                self.paths = [[], []]
                self._build_paths()
            except Exception as e:
                raise e
        # Build timestamps
        self.timestamps = list()
        self._build_timestamp()
        # Returns
        self.initialized = True
        return

    def _read_file(self) -> str:
        """Read the content of the file pointed by `logpath`

        Returns:
            str: the content of the log file

        Raises:
            IOError: error at opening the log file
        """
        try:
            with open(self.logpath, 'r') as f:
                print(f"[INFO] Reading {self.logpath} ...")
                return f.read()
        except IOError:
            raise IOError(f"error at opening ({self.logpath})")

    def _read_log(self):
        """Read log file `logpath` to fill up `raw_inputs` with cleaned string entries

        Filters : comments, empty lines and malformed lines
        """
        for l in self._read_file().splitlines():
            if l:  # line is not empty
                # Match pattern
                # https://www.tutorialspoint.com/python/python_reg_expressions.htm
                if re.match(r'#.*$', l, re.M):
                    continue
                else:
                    tmp = l.split(' ')
                    # TODO : rendre dynamique cette valeur avec
                    # le format donne par le header
                    if len(tmp) < 4:
                        print(f"[WARNING] {l} is a malformed line")
                        continue
                    self.raw_inputs.append(tuple([
                        float(tmp[0]),
                        0 if tmp[1] == 'D' else 1,
                        tmp[2],
                        tmp[3]]))

    def _clean_log(self):
        """Clean logs from `raw_inputs` to `inputs`

        Filters : rnti65535
        Extract ids and values from pattern id123, 'id': 123
        Transform the string entry in tuple entry
        At the end, `input` is made immutable for the rest of the program

        Raises:
            ValueError : Error at parsing a line
        """
        # sort by timestamp. important assumption for the next methods
        self.raw_inputs.sort(key=operator.itemgetter(0))
        # patterns to detect
        match_ids = re.compile("([a-zA-Z]+)([0-9]+)")
        # match_emptyrnti = re.compile("rnti65535")
        for e in self.raw_inputs:
            # an entry is a timestamp, a direction,
            # an in point an out point, a size,
            # a list of glibal context data id and local data id

            # skip lines which matches the following re
            if re.search("rnti65535", e[3]):
                continue

            # process line
            try:
                e_points = e[2].split('--')
                dataids = e[3].split(':')
                if len(dataids) < 3:
                    continue
                ptmp = {}
                # properties values
                if dataids[0] != '':
                    for p in dataids[0].split('.'):
                        try:
                            dip = match_ids.match(p).groups()
                        except Exception:
                            continue
                        else:
                            ptmp[dip[0]] = dip[1]
                # global context ids
                ctmp = {}
                if dataids[1] != '':
                    for c in dataids[1].split('.'):
                        try:
                            # dic[0] is the global context identifier
                            # dic[1] the value associated
                            dic = match_ids.match(c).groups()
                        except Exception:
                            continue
                        else:
                            ctmp[dic[0]] = dic[1]
                            if dic[0] not in self.dataids:
                                self.dataids.append(dic[0])
                dtmp = {}
                # local context ids
                if dataids[2] != '':
                    for d in dataids[2].split('.'):
                        try:
                            # did[0] is the local context identifier
                            # did[1] the value associated
                            did = match_ids.match(d).groups()
                        except Exception:
                            continue
                        else:
                            if did[0] not in dtmp:
                                dtmp[did[0]] = did[1]
                            else:  # case we have multiple value for the same id
                                if isinstance(dtmp[did[0]], list):
                                    dtmp[did[0]].append(did[1])
                                else:
                                    tmpl = [dtmp[did[0]], did[1]]
                                    del dtmp[did[0]]
                                    dtmp[did[0]] = tmpl
                            if did[0] not in self.dataids:
                                self.dataids.append(did[0])

                self.inputs.append((
                        e[0],
                        e[1],
                        e_points[0],
                        e_points[1],
                        ptmp,
                        ctmp,
                        dtmp))
            except Exception:
                raise ValueError(f"Error at parsing line {e}")
        self.inputs = make_immutable_list(self.inputs)

    def _build_points(self):
        """Build graph of measurement `points` and find in and out points
        """
        # Build graph
        for e in self.raw_inputs:
            e_points = e[2].split('--')  # [0] is src point and [1] is dest point
            if e_points[0] not in self.points:
                # list of pointers and direction 0 for D and 1 for U
                self.points[e_points[0]] = {}
                self.points[e_points[0]]['next'] = []
                self.points[e_points[0]]['count'] = 0
                self.points[e_points[0]]['dir'] = [e[1]]
            if e_points[1] not in self.points[e_points[0]]['next']:
                # Get combinations of dest point
                # ex. rlc.seg.um : rlc, rlc.seg, rlc.seg.um
                destpt = e_points[1].split('.')
                for i in range(len(destpt)):
                    tmps = ""
                    j = 0
                    while j <= i:
                        tmps += f"{destpt[j]}."
                        j += 1
                    self.points[e_points[0]]['next'].append(tmps[:-1])
            if e_points[1] not in self.points:
                self.points[e_points[1]] = {}
                self.points[e_points[1]]['next'] = []
                self.points[e_points[1]]['count'] = 1
                self.points[e_points[1]]['dir'] = [e[1]]
            self.points[e_points[0]]['count'] += 1
            if e[1] not in self.points[e_points[0]]['dir']:
                self.points[e_points[0]]['dir'].append(e[1])
        
        # The IN and OUT are not fixed in the __init__ before calling this method
        if not hasattr(self, 'pointsInD') or not hasattr(self, 'pointsInU') or not hasattr(self, 'pointsOutD') or not hasattr(self, 'pointsOutU'):
            # Find IN et OUT points dynamically
            tmpD = [x[0] for x,y in self.points if y[1]==0]
            tmpDin = tmpD
            tmpDout = []
            tmpU = [x[0] for x in self.points if x[1]==1]
            tmpUin = tmpU
            tmpUout = []
            for p in self.points:
                # case D
                if p[1] == 0:
                    # if not pointed by anyone, then, it is the input
                    for e in p[0]:
                        tmpDin.remove(e)
                    # if pointed but not in keys, it is the output
                        if e not in tmpD:
                            tmpDout.append(e)
                elif p[1] == 1:
                    # if not pointed by anyone, then, it is the input
                    for e in p[0]:
                        tmpUin.remove(e)
                    # if pointed but not in keys, it is the output
                        if e not in tmpU:
                            tmpUout.append(e)
                else:
                    print(f"[ERROR] Unknown direction for {p[0]} : {p[1]}")
            self.pointsInD  = tmpDin
            self.pointsOutD = tmpDout
            self.pointsInU  = tmpUin
            self.pointsOutU = tmpUout

    def _build_paths(self):
        """Build all possible `paths` in the graph `points`

        BFS is used as algorithm to build all paths possible between an IN and OUT point
        """
        def _find_all_paths(graphP: dict, startP: str, endP: str, pathP=[]):
            tmppath = pathP + [startP]
            if startP == endP:
                return [tmppath]
            if startP not in graphP:
                return []
            paths = []
            for p in graphP[startP]['next']:
                if p not in tmppath:
                    newpaths = _find_all_paths(graphP, p, endP, tmppath)
                    for newpath in newpaths:
                        paths.append(newpath)
            return paths
        # build downlink paths
        for i in self.pointsInD:
            for o in self.pointsOutD:
                self.paths[0].extend(_find_all_paths(self.points, i, o))
        for i in self.pointsInU:
            for o in self.pointsOutU:
                self.paths[1].extend(_find_all_paths(self.points, i, o))
        if len(self.paths[0]) == 0 and len(self.paths[1]) == 0:
            raise Exception("Error no paths found in Downlink nor in Uplink")
        elif len(self.paths[0]) == 0:
            raise Exception("Error, no path found in Downlink")
        elif len(self.paths[1]) == 0:
            raise Exception("Error, no path found in Uplink")

    def _build_timestamp(self):
        """Build `timestamps` a :obj:`list` of float of timestamp
        """
        self.timestamps = list(map(lambda x: x[0], self.raw_inputs))

    def rebuild_packets_journey_seq(self):
        """[DEPRECATED] Rebuild the packets journey sequentially from a list of measure
        Algorithm:
            Process each packet sequentially and try to put into a journey
        Args:
            inputs: ordered and cleaned inputs
        Attributs:
            journeys (:obj:`dict`): the dictionnary containing dictionnaries
            out_journeys (:obj:`list`): the list of journeys prepare for output
        """
        def _measure_ids_in_journey(p_gids: list, p_lids: list, j_gids: list, j_last_element: dict) -> dict:
            """Returns the dict of common identifiers if the measure is in the journey
            Otherwise returns an empty dictionnary
            """
            # for all global ids, first filter
            for k in p_gids:
                if k in j_gids:
                    if p_gids[k] != j_gids[k]:
                        return {}  # False
                else:  # The global context id is not in the contet of this journey, continue
                    return {}  # False
            res_matched = {}
            # for all local ids in measurement point
            for k_lid in p_lids:
                if k_lid in j_last_element[6]:  # if the local ids are present in the 2 points
                    # Case : multiple value for the same identifier
                    if isinstance(j_last_element[6][k_lid], list):
                        match_local_in_list = False
                        for v in j_last_element[6][k_lid]:
                            if p_lids[k_lid] == v:  # We want only one matches the id
                                match_local_in_list = True
                                res_matched[k_lid] = v
                                # remove the multiple value for input to keep only the one used
                                j_last_element[6][k_lid] = v
                                break  # for v in j_last_lids[k_lid]
                        if not match_local_in_list:
                            return {}
                    # Case : normal case, one value per identifier
                    else:
                        if p_lids[k_lid] != j_last_element[6][k_lid]:  # the local id k_lid do not match
                            return {}
                        else:
                            res_matched[k_lid] = p_lids[k_lid]
            return res_matched

        self.journeys = dict()
        self.out_journeys = list()
        if not self.initialized:
            try:
                self(self.logpath)
            except Exception:
                raise Exception("Impossible to rebuild packet because the module has not been initialized correctly")
        
        total_i = len(self.inputs)
        current_i = 0
        for p in self.inputs:  # for all input, try to build the journeys
            current_i += 1
            if current_i % 100 == 0:
                print(f"{current_i} / {total_i}")
            # if current_i > 3000:
            #     break
            # p[0] float : ts
            # p[1] int : direction
            # p[2] str : src point
            # p[3] str : dst point
            # p[4] dict : properties ids
            # p[5] dict : global ids
            # p[6] dict : local ids
            if p[1] == 0:  # Downlink
                tmpIn = self.pointsInD
                tmpOut = self.pointsOutD
            else:  # Uplink
                tmpIn = self.pointsInU
                tmpOut = self.pointsOutU

            if p[2] in tmpIn:  # this is a packet in arrival, create a new journey
                newid = len(self.journeys)
                self.journeys[newid] = dict()
                self.journeys[newid]['dir'] = p[1]
                self.journeys[newid]['glob'] = p[5]  # global ids as a first filter
                self.journeys[newid]['ts_in'] = p[0]  # timestamp of arrival
                self.journeys[newid]['set'] = list()  # set measurements of ids in inputs for this journey
                self.journeys[newid]['set'].append(self.inputs.index(p))
                self.journeys[newid]['set_ids'] = dict()
                # tmp_list = [f"uid{newid}"]
                # for l in p[6]:
                #     tmp_list.append(f"{l}{p[6][l]}")
                self.journeys[newid]['set_ids'] = {'uid': newid}
                self.journeys[newid]['set_ids'].update(p[6])
                self.journeys[newid]['next_points'] = self.points[p[2]]['next']  # list of possible next points
                self.journeys[newid]['last_point'] = p[2]
                self.journeys[newid]['completed'] = False  # True if the journey is complete
            else:  # this packet should be already followed somewhere
                matched_key = None
                matched_ids = dict()
                matched_seg = False
                seg_new_journey = dict()
                for i in self.journeys:  # for all keys (ids) in journeys
                    # Case : journey already completed
                    # Assumption : no segmentation at the out points
                    if self.journeys[i]['completed']:
                        continue  # for i in self.journeys

                    # Case : wrong direction
                    if p[1] != self.journeys[i]['dir']:
                        continue  # for i in self.journeys

                    # Case : segmentation
                    # False Asumption : all the segmentation will occurs before the measure of the next point
                    if p[2] == self.journeys[i]['last_point']:
                        if len(self.journeys[i]['set']) > 1:
                            matched_ids = _measure_ids_in_journey(
                                p[5],
                                p[6],
                                self.journeys[i]['glob'],
                                self.inputs[self.journeys[i]['set'][-2]])
                            if matched_ids:  # this is a fork from the point before the last point, a segmentation
                                matched_seg = True
                                seg_new_journey = deepcopy(self.journeys[i]) # deep copy the journey
                                seg_new_journey['set'].pop() # we remove the last element of the set because we forked
                                # TODO: what to do when the value is exactly the same ?
                                seg_new_journey['set'].append(self.inputs.index(p))
                                seg_new_journey['set_ids'].update(matched_ids)
                                seg_new_journey['last_point'] = p[2]
                                break  # for i in self.journeys

                    # Case : not expected next measurement point
                    if self.journeys[i]['next_points'] is not None and not p[2] in self.journeys[i]['next_points']:
                        continue  # for i in self.journeys

                    # if len(p[5]) > 0:  # case where global context is irrelevant, lower layers
                    # Case : packet as candidate to join this journey
                    matched_ids = _measure_ids_in_journey(
                        p[5],
                        p[6],
                        self.journeys[i]['glob'],
                        self.inputs[self.journeys[i]['set'][-1]])
                    if not matched_ids:  # No match
                        continue  # for i in self.journeys

                    matched_key = i
                    break

                # Case : A segmentation has been found,
                # add seg_new_journeys to the dict
                if matched_seg:
                    newidseg = len(self.journeys)
                    self.journeys[newidseg] = seg_new_journey
                    continue # for p in self.inputs

                # Case : This measure could not be added to a journey
                if matched_key is None:
                    continue  # for p in self.inputs
                
                # At this point, we have a journey id to add this measure
                self.journeys[matched_key]['set'].append(self.inputs.index(p))
                self.journeys[matched_key]['set_ids'].update(matched_ids)
                
                if p[3] in tmpOut:  # this is the last input before the great farewell
                    self.journeys[matched_key]['next_points'] = None
                    self.journeys[matched_key]['ts_out'] = p[0]
                    self.journeys[matched_key]['completed'] = True
                else:  # this is not the last input
                    self.journeys[matched_key]['next_points'] = self.points[p[2]]['next']
                    self.journeys[matched_key]['last_point'] = p[2]

        # retrieves all journey to build out_journeys
        for j in self.journeys:
            # Case : The journey is incomplete
            if not self.journeys[j]['completed']:
                continue
            for e in self.journeys[j]['set']: # for all elements in set of ids
                e_tmp = self.inputs[e]
                tmp_str = f"uid{j}.{dict_ids_to_str(self.journeys[j]['glob'])}.{dict_ids_to_str(e_tmp[6])}"
                self.out_journeys.append((
                    epoch_to_datetime(e_tmp[0]),
                    'D' if e_tmp[1] == 0 else 'U',
                    f"{e_tmp[2]}--{e_tmp[3]}",
                    e_tmp[4],
                    tmp_str))
        try:
            with open("latseq.lseqj", 'w+') as f:
                print(f"[INFO] Writing latseq.lseqj ...")
                for e in self.yield_clean_inputs():
                    f.write(f"{e}\n")
        except IOError as e:
            print(f"[ERROR] on open({self.logpath})")
            print(e)
            raise e

    def rebuild_packets_journey_recursively(self):
        """Rebuild the packets journey from a list of measure recursively
        Algorithm:
            for each input packet, try to rebuild the journey with the next measurements (depth limited)
        Args:
            inputs: ordered and cleaned inputs
        Attributs:
            journeys (:obj:`dict`): the dictionnary of journey
            out_journeys (:obj:`list`): the list of journeys prepare for output
        """
        self.journeys = dict()
        self.out_journeys = list()
        # Case: the instance has not been initialized correctly
        if not self.initialized:
            try:
                self(self.logpath)
            except Exception:
                raise Exception("Impossible to rebuild packet because this instance of latseq_log has not been initialized correctly")
        
        nb_meas = len(self.inputs)  # number of measure in self.inputs
        info_meas = {}
        list_meas = list(range(nb_meas))  # list of measures not in a journey
        point_added = {}  # point added
        pointer = 0  # base pointer on the measure in self.inputs for the current journey's input
        local_pointer = 0  # pointer on the current tested measure candidate for the current journey

        def _measure_ids_in_journey(p_gids: list, p_lids: list, j_gids: list, j_last_element: dict) -> dict:
            """Returns the dict of common identifiers if the measure is in the journey
            Otherwise returns an empty dictionnary
            """
            # for all global ids, first filter
            for k in p_gids:
                if k in j_gids:
                    if p_gids[k] != j_gids[k]:
                        return {}  # False
                else:  # The global context id is not in the contet of this journey, continue
                    return {}  # False
            res_matched = {}
            # for all local ids in measurement point
            for k_lid in p_lids:
                if k_lid in j_last_element[6]:  # if the local ids are present in the 2 points
                    # Case : multiple value for the same identifier
                    if isinstance(j_last_element[6][k_lid], list):
                        match_local_in_list = False
                        for v in j_last_element[6][k_lid]:
                            if p_lids[k_lid] == v:  # We want only one matches the id
                                match_local_in_list = True
                                res_matched[k_lid] = v
                                # remove the multiple value for input to keep only the one used
                                j_last_element[6][k_lid] = v
                                break  # for v in j_last_lids[k_lid]
                        if not match_local_in_list:
                            return {}
                    # Case : normal case, one value per identifier
                    else:
                        if p_lids[k_lid] != j_last_element[6][k_lid]:  # the local id k_lid do not match
                            return {}
                        else:
                            res_matched[k_lid] = p_lids[k_lid]
            return res_matched

        def _get_next(listP: list, endP: int, pointerP: int) -> int:
            pointerP += 1
            while pointerP not in listP and pointerP < endP - 1:
                pointerP += 1
            return pointerP

        def _rec_rebuild(pointerP: int, local_pointerP: int, parent_journey_id: int) -> bool:
            """rebuild journey from a parent measure
            Args:
                pointerP (int): the index in inputs of the parent measure
                local_pointerP (int): the index in inputs of the current measure candidate for the journey
                parent_journey_id (int): the id of the current journey
            Returns:
                bool: if the journey is completed
            """
            seg_list = {}
            # max local pointer to consider. DEPTH_TO_SEARCH impact the algorithm's speed
            max_local_pointer = min(local_pointerP + DEPTH_TO_SEARCH_PKT, nb_meas)
            # LOOP: the journey is not completed and we still have local_pointer to consider
            while not self.journeys[parent_journey_id]['completed'] and local_pointerP < max_local_pointer:
                # if local_pointerP not in list_meas:
                #     print(f"error at removing : {local_pointerP}")
                #     continue
                tmp_p = self.inputs[local_pointerP]

                # Case: wrong direction
                if tmp_p[1] != self.journeys[parent_journey_id]['dir']:
                    local_pointerP = _get_next(list_meas, nb_meas, local_pointerP)
                    continue
                
                # Case: the measurement point is too far away
                # and tmp_p[2] not in self.journeys[parent_journey_id]['last_points']
                if tmp_p[2] not in self.journeys[parent_journey_id]['next_points']:
                    local_pointerP = _get_next(list_meas, nb_meas, local_pointerP)
                    continue

                # Case: the measurement point is an input
                if tmp_p[1] == 0:  # Downlink
                    if tmp_p[2] in self.pointsInD:
                        local_pointerP = _get_next(list_meas, nb_meas, local_pointerP)
                        continue
                else:  # Uplink
                    if tmp_p[2] in self.pointsInU:
                        local_pointerP = _get_next(list_meas, nb_meas, local_pointerP)
                        continue


                # Case: Concatenation
                # TODO : gestion de la concatenation
                #   Play with list_meas.remove(local_pointerP)

                # Case: Normal
                # Here get the first occurence who is matching
                matched_ids = _measure_ids_in_journey(
                    tmp_p[5],
                    tmp_p[6],
                    self.journeys[parent_journey_id]['glob'],
                    self.inputs[self.journeys[parent_journey_id]['set'][-1]]
                )
                if not matched_ids:
                    local_pointerP = _get_next(list_meas, nb_meas, local_pointerP)
                    continue

                # Case: find a match
                # list_meas.remove(local_pointerP)
                print(f"Add {local_pointerP} to {parent_journey_id}")
                if local_pointerP not in point_added:
                    point_added[local_pointerP] = [parent_journey_id]
                else:
                    point_added[local_pointerP].append(parent_journey_id)
                seg_local_pointer = _get_next(list_meas, nb_meas, local_pointerP)
                # Case : search for segmentation
                # Find all forks possible
                # seg local pointer to consider for segmentations.
                #   DEPTH_TO_SEARCH_FORKS impact the algorithm's complexity
                max_seg_pointer = min(local_pointerP + DEPTH_TO_SEARCH_FORKS, nb_meas - 1)
                # LOOP: we still have a seg local pointer to consider
                while seg_local_pointer < max_seg_pointer:
                    seg_tmp_p = self.inputs[seg_local_pointer]
                    
                    # Case: wrong direction
                    if seg_tmp_p[1] != self.journeys[parent_journey_id]['dir']:
                        seg_local_pointer = _get_next(list_meas, nb_meas, seg_local_pointer)
                        continue
                    # Case: the src point are different, not a candidate for segmentation
                    if seg_tmp_p[2] != tmp_p[2]:
                        seg_local_pointer = _get_next(list_meas, nb_meas, seg_local_pointer)
                        continue

                    seg_matched_ids = _measure_ids_in_journey(
                        seg_tmp_p[5],
                        seg_tmp_p[6],
                        self.journeys[parent_journey_id]['glob'],
                        self.inputs[self.journeys[parent_journey_id]['set'][-1]])
                    # Case: find a match, then a segmentation
                    if seg_matched_ids:
                        if local_pointerP not in seg_list:
                            seg_list[local_pointerP] = {}
                        seg_list[local_pointerP][seg_local_pointer] = seg_matched_ids
                        seg_local_pointer = _get_next(list_meas, nb_meas, seg_local_pointer)
                        continue
                    seg_local_pointer = _get_next(list_meas, nb_meas, seg_local_pointer)

                # At this point, we have completed all the possible fork
                self.journeys[parent_journey_id]['set'].append(self.inputs.index(tmp_p))
                self.journeys[parent_journey_id]['set_ids'].update(matched_ids)
            
                if tmp_p[3] in tmpOut:  # this is the last input before the great farewell
                    self.journeys[parent_journey_id]['next_points'] = None
                    self.journeys[parent_journey_id]['ts_out'] = tmp_p[0]
                    self.journeys[parent_journey_id]['completed'] = True
                else:  # continue to rebuild journey
                    self.journeys[parent_journey_id]['next_points'] = self.points[tmp_p[2]]['next']
                    local_pointerP = _get_next(list_meas, nb_meas, local_pointerP)

            # Case: We finished to rebuild the first journey,
            #   We find segmentation for one or more points
            #   Retrieves all point of the first journey
            #   If brother(s) for a point for this first journey
            #   rebuild new journey from this brother to the end
            #   Looks like a tree
            if seg_list and self.journeys[parent_journey_id]['completed']:
                for p in self.journeys[parent_journey_id]['set']:
                    if p in seg_list:  # There is a brother
                        # For all brothers
                        for s in seg_list[p]:  # seg_local_pointer : seg_matched_ids
                            # Create a new path
                            # TODO: what to do when the value is exactly the same ?
                            seg_p = self.inputs[s]
                            segid = len(self.journeys)
                            self.journeys[segid] = deepcopy(self.journeys[parent_journey_id])
                            self.journeys[segid]['set_ids']['uid'] = segid
                            # Remove all elements after p
                            del self.journeys[segid]['set'][self.journeys[segid]['set'].index(p):]
                            self.journeys[segid]['set'].append(s)
                            self.journeys[segid]['completed'] = False
                            # TODO: check if no collision with set_ids
                            self.journeys[segid]['set_ids'].update(seg_list[p][s])
                            print(f"Add {s} to {segid}")
                            if s not in point_added:
                                point_added[s] = [segid]
                            else:
                                point_added[s].append(segid)
                            # list_meas.remove(seg_local_pointer)
                            if seg_p[3] in tmpOut:  # this is the last input before the great farewell
                                self.journeys[segid]['next_points'] = None
                                self.journeys[segid]['ts_out'] = seg_p[0]
                                self.journeys[segid]['completed'] = True
                                continue
                            self.journeys[segid]['next_points'] = self.points[seg_p[2]]['next']
                            seg_local_pointer_next = _get_next(list_meas, nb_meas, s)
                            _rec_rebuild(seg_local_pointer, seg_local_pointer_next, segid)
                            #pointerP = _get_next(list_meas, nb_meas, pointerP)

            return self.journeys[parent_journey_id]['completed']

        # LOOP: for all inputs, try to build the journeys
        while pointer < nb_meas:
            # current_i += 1
            # if current_i % 100 == 0:
            #     print(f"{current_i} / {total_i}")
            # if pointer > 2000:
            #     break
            p = self.inputs[pointer]
            # p[0] float : ts
            # p[1] int : direction
            # p[2] str : src point
            # p[3] str : dst point
            # p[4] dict : properties ids
            # p[5] dict : global ids
            # p[6] dict : local ids

            # Get the correct set of IN/OUT for the current direction
            if p[1] == 0:  # Downlink
                tmpIn = self.pointsInD
                tmpOut = self.pointsOutD
            else:  # Uplink
                tmpIn = self.pointsInU
                tmpOut = self.pointsOutU

            # Case: the current measure is not an input measure, continue
            if p[2] not in tmpIn:
                pointer += 1
                while pointer not in list_meas and pointer < nb_meas:
                    pointer += 1
                continue

            # this is a packet in arrival, create a new journey
            newid = len(self.journeys)
            self.journeys[newid] = dict()
            self.journeys[newid]['dir'] = p[1]  # direction for this journey
            self.journeys[newid]['glob'] = p[5]  # global ids as a first filter
            self.journeys[newid]['ts_in'] = p[0]  # timestamp of arrival
            self.journeys[newid]['set'] = list()  # set measurements of ids in inputs for this journey
            self.journeys[newid]['set'].append(self.inputs.index(p))
            self.journeys[newid]['set_ids'] = dict()  # dict of local ids
            self.journeys[newid]['set_ids'] = {'uid': newid}
            self.journeys[newid]['set_ids'].update(p[6])
            self.journeys[newid]['next_points'] = self.points[p[2]]['next']  # list of possible next points
            if self.journeys[newid]['set'][-1] not in point_added:
                point_added[self.journeys[newid]['set'][-1]] = [newid]
            self.journeys[newid]['path'] = 0  # path number of this journey according to self.paths
            # self.journeys[newid]['last_points'] = [p[2]]
            self.journeys[newid]['completed'] = False  # True if the journey is complete
            # list_meas.remove(pointer)  # Remove from the list
            local_pointer = _get_next(list_meas, nb_meas, pointer)
            # Try to rebuild the journey from this packet
            # Assumption: the measures are ordered by timestamp,
            #   means that the next point is necessary after the current
            #   input point in the list of inputs
            _rec_rebuild(pointer, local_pointer, newid)
            pointer = _get_next(list_meas, nb_meas, pointer)

        # retrieves all journey to build out_journeys
        added_out_j = {}
        for j in self.journeys:
            # Case : The journey is incomplete
            if not self.journeys[j]['completed']:
                continue
            for e in self.journeys[j]['set']: # for all elements in set of ids
                e_tmp = self.inputs[e]
                if e not in added_out_j:  # create a new entry for this point in out journeys
                    added_out_j[e] = len(self.out_journeys)
                    tmp_uid = self.journeys[j]['set_ids']['uid']
                    tmp_str = f"uid{tmp_uid}.{dict_ids_to_str(self.journeys[j]['glob'])}.{dict_ids_to_str(e_tmp[6])}"
                    self.out_journeys.append([
                        e_tmp[0],  # [0] : timestamp
                        'D' if e_tmp[1] == 0 else 'U',  # [1] : dir
                        f"{e_tmp[2]}--{e_tmp[3]}", # [2] : segment
                        e_tmp[4],  # [3] : properties
                        tmp_str])  # [4] : data id
                else:  # update the current entry
                    self.out_journeys[added_out_j[e]][4] = f"uid{self.journeys[j]['set_ids']['uid']}." + self.out_journeys[added_out_j[e]][4]

                # points latency
                tmp_point = self.points[e_tmp[2]]
                if 'duration' not in tmp_point:
                    tmp_point['duration'] = {}
                if e_tmp[2] in self.pointsInD or e_tmp[2] in self.pointsInU:  # Is an in points
                    tmp_point['duration'][tmp_uid] = 0
                else:  # Is a mid point because out could not be in e_tmp[2]
                    current_index = self.journeys[j]['set'].index(e)
                    prev_ts = self.inputs[self.journeys[j]['set'][current_index - 1]][0]
                    tmp_point['duration'][tmp_uid] = e_tmp[0] - prev_ts
        self.out_journeys.sort(key=operator.itemgetter(0))
        orphans = 0
        for e in range(nb_meas):
            if e not in point_added:
                print(f"{e} : {self.inputs[e]} is missing in journeys (completed or not)")
                orphans += 1
        print(f"{orphans} orphans / {nb_meas}")

        # Saves to file type lseqj
        try:
            with open("latseq.lseqj", 'w+') as f:
                print(f"[INFO] Writing latseq.lseqj ...")
                for e in self.yield_clean_inputs():
                    f.write(f"{e}\n")
        except IOError as e:
            print(f"[ERROR] on open({self.logpath})")
            print(e)
            raise e


    # GETTERS
    def get_filename(self) -> str:
        """Get filename used for this instance of latseq_logs
        Returns:
            filename (str)
        """
        return self.logpath.split('/')[-1]

    def get_list_of_points(self) -> list:
        """Get the list of points in the file
        Returns:
            points (:obj:`list` of str)
        """
        return list(self.points.keys())

    def get_list_timestamp(self) -> list:
        """Get the timestamps in `input` file
        Returns:
            list of timestamps
        """
        if not self.timestamps:
            self._build_timestamp()
        return self.timestamps

    def get_log_file_stats(self) -> dict:
        """Get stats of the logfile
        Returns:
            file_stats (:obj:`dict`): name, nb_raw_meas, nb_meas, points
        """
        return {
            "name": self.logpath,
            "nb_raw_meas": len(self.raw_inputs),
            "nb_meas": len(self.inputs),
            "points": self.get_list_of_points()
            }

    def get_paths(self) -> tuple:
        """Get paths found in the file
        Returns:
            paths (:obj:`tuple` of :obj:`list`): 0 for Downlink paths and 1 for Uplink paths
        """
        if len(self.paths[0]) == 0 and len(self.paths[1]) == 0:
            self._build_paths()
        return (self.paths[0], self.paths[1])

    def yield_clean_inputs(self):
        """Yielder for cleaned inputs
        Yields:
            str: A line of input
        Raises:
            ValueError : if the entry in out_journeys is malformed
        """
        try:
            for e in self.out_journeys:
                yield f"{epoch_to_datetime(e[0])} {e[1]} (len{e[3]['len']})\t{e[2]}\t{e[4]}"
                # yield f"{e[0]} {e[1]} {e[2]} {e[4]}"
        except Exception:
            raise ValueError(f"{e} is malformed")

    def yield_journeys(self):
        """Yielder of journeys
        Yields:
            journey element (:obj:`dict`)
        Raises:
            ValueError: Impossible to yield a journey from self.journeys
            Exception: Impossible to rebuild journeys
        """
        try:
            if not hasattr(self, 'journeys'):
                try:
                    self.rebuild_packets_journey_recursively()
                except Exception:
                    raise Exception("Imposible to rebuild journeys")
            for j in self.journeys:
                yield j
        except Exception:
            raise ValueError(f"Impossible to yield {j}")

    def paths_to_str(self) -> str:
        """Stringify paths
        Returns:
            str: paths
        """
        res = f"Paths found in {self.logpath} \n"
        i, j = 0, 0
        for d in self.get_paths():
            if i == 0:
                res += "Downlink paths\n"
            if i == 1:
                res += "Uplink paths\n"
            for p in d:
                if p:
                    res += f"\tpath {j} : "
                    res += path_to_str(p)
                    res += "\n"
                j += 1
            i += 1
        return res


#
# STATISTICS
#
class latseq_stats:
    """Class of static methods for statistics stuff for latseq
    """
    # PRESENTATION
    @staticmethod
    def str_statistics(statsNameP: str, statsP: dict) -> str:
        """Stringify a statistics

        A statistics here embedded size, average, max, min, quantiles, stdev

        Args:
            statsNameP (str): the title for this stats
            statsP (str): a dictionnary with statistics

        Returns:
            str: the output statistics
        """
        res_str = f"Stats for {statsNameP}\n"
        for dir in statsP:
            if dir == '0':
                res_str += "Values \t\t | \t Downlink\n"
                res_str += "------ \t\t | \t --------\n"
            elif dir == '1':
                res_str += "Values \t\t | \t Uplink\n"
                res_str += "------ \t\t | \t ------\n"
            else:
                continue
            keysD = statsP[dir].keys()
            if 'size' in keysD:
                res_str += f"Size \t\t | \t {statsP[dir]['size']}\n"
            if 'mean' in keysD:
                res_str += f"Average \t | \t {float(statsP[dir]['mean']):.3}\n"
            if 'stdev' in keysD:
                res_str += f"StDev \t\t | \t {float(statsP[dir]['stdev']):.3}\n"
            if 'max' in keysD:
                res_str += f"Max \t\t | \t {float(statsP[dir]['max']):.3}\n"
            if 'quantiles' in keysD:
                if len(statsP[dir]['quantiles']) == 5:
                    res_str += f"[75..90%] \t | \t {float(statsP[dir]['quantiles'][4]):.3}\n"
                    res_str += f"[50..75%] \t | \t {float(statsP[dir]['quantiles'][3]):.3}\n"
                    res_str += f"[25..50%] \t | \t {float(statsP[dir]['quantiles'][2]):.3}\n"
                    res_str += f"[10..25%] \t | \t {float(statsP[dir]['quantiles'][1]):.3}\n"
                    res_str += f"[0..10%] \t | \t {float(statsP[dir]['quantiles'][0]):.3}\n"
                else:
                    for i in range(len(statsP[dir]['quantiles']),0,-1):
                        res_str += f"Quantiles {i-1}\t | \t {statsP[dir]['quantiles'][i-1]:.3}\n"
            if 'min' in keysD:
                res_str += f"Min \t\t | \t {float(statsP[dir]['min']):.3}\n"
        return res_str

    # GLOBAL_BASED
    @staticmethod
    def mean_separation_time(tsLP: list) -> float:
        """Function to return means time separation between logs

        Args:
            TsLP (:obj:`list` of float): the list of timestamp

        Returns:
            float : mean time separation between log entries

        Raises:
            ValueError: The len of list is < 2
        """
        if len(tsLP) < 2:
            raise ValueError("The length of tsLP is inferior to 2")
        tmp = list()
        for i in range(len(tsLP)-1):
            tmp.append(abs(tsLP[i+1]-tsLP[i]))
        return statistics.mean(tmp)

    # JOURNEYS-BASED
    @staticmethod
    def journeys_latency_statistics(journeysP: dict) -> dict:
        """Function calculate statistics on journey's latency

        Args:
            journeysP (:obj:`dict` of journey): dictionnary of journey

        Returns:
            :obj:`dict`: statistics
        """
        times = [[],[]]
        for j in journeysP:
            if not journeysP[j]['completed']:
                continue
            times[journeysP[j]['dir']].append((
                j,
                (journeysP[j]['ts_out'] - journeysP[j]['ts_in'])*S_TO_MS))
        # {'size': {105, 445}, 'mean': {0.7453864879822463, 19.269811539422896}, 'min': {0.04315376281738281, 0.00476837158203125}, 'max': {8.366107940673828, 445.9710121154785}, 'stdev': {1.6531425844726746, 61.32162047000048}}
        tmp_t = list()
        tmp_t.append([t[1] for t in times[0]])
        tmp_t.append([t[1] for t in times[1]])
        res = {'0' : {}, '1': {}}
        for d in res:
            res[d] = {
                'size': len(times[int(d)]),
                'min': min(tmp_t[int(d)]),
                'max': max(tmp_t[int(d)]),
                'mean': numpy.average(tmp_t[int(d)]),
                'stdev': numpy.std(tmp_t[int(d)]),
                'quantiles': numpy.quantile(tmp_t[int(d)], [0.1, 0.25, 0.5, 0.75, 0.9]),
                'times': times[int(d)]
            }
        return res


    # POINTS-BASED
    def points_latency_statistics(pointsP: dict) -> dict:
        """Function calculate statistics on points' latency

        Args:
            pointsP (:obj:`dict` of points): dictionnary of point

        Returns:
            :obj:`dict`: statistics
        """
        times = [dict(), dict()]
        for p in pointsP:
            if 'duration' not in pointsP[p]:
                continue
            tmp_p = [v * S_TO_MS for v in list(pointsP[p]['duration'].values())]
            if 0 in pointsP[p]['dir']:
                times[0][p] = tmp_p
            if 1 in pointsP[p]['dir']:
                times[1][p] = tmp_p
        res = {'0': {}, '1': {}}
        for d in res:
            dint=int(d)
            for e0 in times[dint]:
                res[d][e0] = {
                    'size': len(times[dint][e0]),
                    'min': min(times[dint][e0]),
                    'max': max(times[dint][e0]),
                    'mean': numpy.average(times[dint][e0]),
                    'stdev': numpy.std(times[dint][e0]),
                    'quantiles': numpy.quantile(times[dint][e0], [0.1, 0.25, 0.5, 0.75, 0.9]),
                    'durations': times[dint][e0]
                }
        return res


#
# MAIN
#

if __name__ == "__main__":
    parser = argparse.ArgumentParser("LatSeq log processing")
    parser.add_argument(
        "-l",
        "--log",
        type=str,
        dest="logname",
        help="Log file",
        required=True
    )

    args = parser.parse_args()

    if args.logname:
        try:
            with open(f"lseq_data_{args.logname.split('/')[-1]}.pkl", 'rb') as fin:
                try:
                    lseq = pickle.load(fin)
                except EOFError:
                    raise FileNotFoundError
        except FileNotFoundError:
            try:
                lseq = latseq_log(args.logname)
            except Exception as e:
                raise(e)
                print(f"[ERROR] On creating a lseq element {args.logname}")
                exit()
        if not hasattr(lseq, 'journeys') or not lseq.journeys:
            lseq.rebuild_packets_journey_recursively()
        with open(f"lseq_data_{lseq.get_filename()}.pkl", 'wb') as fout:
            pickle.dump(lseq, fout, pickle.HIGHEST_PROTOCOL)
        
        print(lseq.get_list_of_points())
        print(lseq.paths_to_str())
        print(latseq_stats.str_statistics("Journeys latency", latseq_stats.journeys_latency_statistics(lseq.journeys)))
        print("Latency for points")
        tmp_stats_points = latseq_stats.points_latency_statistics(lseq.points)
        for dir in tmp_stats_points:
            for p in tmp_stats_points[dir]:
                print(latseq_stats.str_statistics(f"Point Latency for {p}", {dir : tmp_stats_points[dir][p]}))
