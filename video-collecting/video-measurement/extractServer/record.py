import argparse
import concurrent.futures
import copy
import ipaddress
import multiprocessing
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
import json
from json import JSONEncoder
import logging
import traceback
import pycurl

import icmplib
import requests

SAVE_DIR = ""


class Bucket:
    def __init__(self, id):
        self.id = id
        self.peers = []


class Query:
    def __init__(self, id, ts, uid):
        self.id = id
        self.answer = []
        self.create_time = ts
        self.child = []
        self.uid = uid
        self.parent = None


class Response:
    def __init__(self, id, ts, uid):
        self.id = id
        self.uid = uid
        self.create_time = ts
        self.parent = []


class Provider:
    def __init__(self, id, ts, uid):
        self.id = id
        self.uid = uid
        self.create_time = ts
        self.parent = None


class Address:
    def __init__(self, ip, ip_type, port, protocol):
        self.ip = ip
        self.ip_type = ip_type
        self.port = port
        self.protocol = protocol
        self.rtt = None
        self.ip_hop = None


class Stats:
    def __init__(self, cid, ipfs_hop, providers, num_blocks, content_size,
                 resolve_time, download_time, actual_provider):
        self.cid = cid
        self.ipfs_hop = ipfs_hop
        self.providers = providers
        self.num_blocks = num_blocks
        self.content_size = content_size
        self.resolve_time = resolve_time
        self.download_time = download_time
        self.actual_provider = actual_provider


class StatsEncoder(JSONEncoder):
    def default(self, o: Stats):
        json_string = o.__dict__
        providers = json_string['providers']
        actual_providers = json_string['actual_provider']
        if providers is not None and actual_providers is not None:
            providers_new = copy.deepcopy(providers)
            actual_providers_new = copy.deepcopy(actual_providers)
            for key in providers.keys():
                # logging.info(f'{key} => {type(providers[key])} => {providers[key]}')
                providers_new[key] = [ob.__dict__ for ob in providers[key]]

            for key in actual_providers.keys():
                actual_providers_new[key] = [ob.__dict__ for ob in actual_providers[key]]
            json_string['providers'] = providers_new
            json_string['actual_provider'] = actual_providers_new
        return json_string


def add_parent(query_target: Query, q: Query):
    """
    add parents for q if exist
    :param query_target: query to check
    :param q: new query q
    :return: True if added to at least one node
    """
    for response in query_target.answer:
        if q.id == response.id:
            try:
                # case child exist
                index = query_target.child.index(q)
            except Exception:
                # case new child
                query_target.child.append(q)
            if q.parent is None:
                q.parent = [query_target]
            else:
                q.parent.append(query_target)
    if len(query_target.child) > 0:
        for i in query_target.child:
            add_parent(i, q)


def find_query(query_target: Query, id):
    if query_target.id == id:
        return query_target
    else:
        if len(query_target.child) > 0:
            for i in query_target.child:
                answer = find_query(i, id)
                if answer is not None:
                    return answer
        else:
            return None
    return None


def find_depth(node: Query):
    """
    find the depth of the current node
    :param node: current node
    :return: the depth of the node
    """
    node = node.parent
    if node is not None and len(node) > 0:
        for parent in node:
            return 1 + find_depth(parent)
    return 1


def analyse_ipfs_hops(cid, result_host_dic, visual=False):
    """
    analyze how many ipfs hop takes
    :param cid: cid of the object
    :param result_host_dic: a dict contains [provider : which peer responded this provider]
    :param visual: bool for visualization out put
    :return: cid and max hop the ipfs query traveled
    """
    logging.info(f'CID {cid} = {result_host_dic}')
    root_query = []
    all_query = []
    all_provider = []
    all_response = []
    dht_bucket = []
    uid = 0
    with open(os.path.join(SAVE_DIR, f'{cid}_dht.txt'), 'r') as stdin:
        bucket_id = 0
        current_bucket = None
        for line in stdin.readlines():
            if "Bucket" in line:
                line = line.replace(" ", "")
                index = line.find("Bucket")
                try:
                    # deal with 2 digit id
                    bucket_id = int(line[index + 6:index + 8])
                except Exception:
                    # case of 1 digit id
                    bucket_id = int(line[index + 6:index + 7])
                current_bucket = Bucket(bucket_id)
                dht_bucket.append(current_bucket)
                continue
            elif "Peer" in line or "DHT" in line:
                continue
            else:
                # bucket reading
                line = line.split(" ")
                # case we have @ at the output
                if line[2] == "@":
                    # print(line[3])
                    current_bucket.peers.append(line[3])
                else:
                    # print(line[4])
                    if line[4] != "":
                        current_bucket.peers.append(line[4])

    with open(os.path.join(SAVE_DIR, f'{cid}_provid.txt'), 'r') as stdin:
        for line in stdin.readlines():
            if line[0] == '\t':
                continue
            line = line.replace("\n", "")
            index = line.find(": ")
            ts = line[:index]
            line = line[index + 1:]
            line = line.split(" ")
            if "querying" in line:
                cid = line[-1]
                q = Query(cid, ts, uid)
                uid += 1
                # find if parent exit or not
                for i in root_query:
                    add_parent(i, q)
                # no parent = root query
                if q.parent is None:
                    root_query.append(q)
                all_query.append(q)
            elif "says" in line:
                # case answer
                res_id = line[line.index("says") - 1]
                answer_start_index = line.index("use") + 1
                # find original query
                q = None
                for query in root_query:
                    q = find_query(query, res_id)
                    if q is not None:
                        break
                for index in range(answer_start_index, len(line)):
                    response = None
                    for r in all_response:
                        if r.id == line[index]:
                            response = r
                            break
                    if response is None:
                        response = Response(line[index], ts, uid)
                        all_response.append(response)
                        uid += 1
                    response.parent.append(q)
                    q.answer.append(response)
            elif "provider:" in line:
                provider = Provider(line[-1], ts, uid)
                uid += 1
                all_provider.append(provider)
    # case of no exist
    # if len(all_provider) == 0:
    #     return 0, -1
    # map provider and result record, and analyse hop info
    host_result_dic = dict(zip(result_host_dic.values(), result_host_dic.keys()))
    max_hop = -1
    for query in all_query:
        if query.id in host_result_dic.keys():
            temp_hop = find_depth(query)
            if temp_hop > max_hop:
                max_hop = temp_hop
    # case of visualization file output
    if visual:
        output_list = []
        level_list = root_query.copy()
        # map root to dht bucket:
        for query in root_query:
            for bucket in dht_bucket:
                if query.id in bucket.peers:
                    query.parent = [f'Bucket {bucket.id}']
                    break
        # start to analysis hop information
        root_level = True
        while len(level_list) > 0:
            temp_list = []
            temp_level_list = []
            for i in level_list:
                # update for existing node
                added = False
                for j in temp_list:
                    if j['id'] == i.id:
                        # if i.parent.id not in j['parents']:
                        j['parents'] += [x.id for x in i.parent]
                        added = True
                        break
                if added:
                    continue
                # case for new node
                peer = {'id': i.id}
                if root_level is True:
                    if i.parent is not None:
                        peer['parents'] = i.parent
                else:
                    if i.parent is not None:
                        peer['parents'] = [x.id for x in i.parent]
                temp_list.append(peer)
                if type(i) == Query:
                    if len(i.child) > 0:
                        temp_level_list += i.child
            output_list.append(temp_list)
            level_list = temp_level_list
            root_level = False

        # # read actual peer who provided answer from daemon
        # with open('daemon.txt', 'r') as stdin:
        #     result_host_dic = {}
        #     for line in stdin.readlines():
        #         if "cid" not in line:
        #             continue
        #         index = line.find("cid")
        #         line = line.replace("\n", "")
        #         line = line[index:]
        #         line = line.split(" ")
        #         result_host_dic[line[5]] = line[3]

        # map final provider to each peer
        temp_list = []
        for index in range(len(all_provider)):
            provider = all_provider[index]
            peer = {'id': f'Provider {index}',
                    # 'parents': []}
                    'parents': [result_host_dic[provider.id]]}
            temp_list.append(peer)
        output_list.append(temp_list)
        # adding bucket into output
        temp_list = []
        for bucket in dht_bucket:
            peer = {'id': f'Bucket {bucket.id}'}
            temp_list.append(peer)
        output_list.insert(0, temp_list)

        with open('visualization/node_modules/@nitaku/tangled-tree-visualization-ii/data.json', 'w') as fout:
            json.dump(output_list, fout)
    return cid, max_hop


def analyse_storage(cid):
    """
    Parse the num_blocks and content_size info from cid_storage.txt
    :param cid: cid of the object
    :return: number of blocks and the size of the content
    """
    size = 0
    num_blocks = -1
    with open(os.path.join(SAVE_DIR, f'{cid}_storage.txt'), 'r') as stdin:
        for line in stdin.readlines():
            # The output of the ipfs dag stat <cid> command is in the form of "Size: 152361, NumBlocks: 1\n"
            if "Size" in line:
                line = line.split(",")
                size = line[0].split(" ")[1]
                num_blocks = line[1].split(" ")[2]
                num_blocks = num_blocks.split("\n")[0]
    return num_blocks, size


def analyse_latency(cid):
    """
    Parse the resolve_time and download_time info from cid_latency.txt
    :param cid: cid of the object
    :return: time to resolve the source of the content and time to download the content
    """
    resolve_time = 0
    download_time = 0
    with open(os.path.join(SAVE_DIR, f'{cid}_latency.txt'), 'r') as stdin:
        for line in stdin.readlines():
            """
            The output of the ipfs get <cid> command is in the form of:
            Started: 02-19-2022 01:51:16
            Resolve Ended: 02-19-2022 01:51:16
            Resolve Duraution: 0.049049
            Download Ended: 02-19-2022 01:51:16
            Download Duraution: 0.006891
            Total Duraution: 0.055940
            """

            if "Resolve Duraution:" in line:
                resolve_time = line.split(": ")[1]
                resolve_time = resolve_time.split("\n")[0]

            if "Download Duraution:" in line:
                download_time = line.split(": ")[1]
                download_time = download_time.split("\n")[0]

    return resolve_time, download_time


def analyse_latency_gateway(cid):
    """
    Parse the resolve_time and download_time info from cid_latency.txt
    :param cid: cid of the object
    :return: time to resolve the source of the content and time to download the content
    """
    resolve_time = 0
    download_time = 0
    with open(os.path.join(SAVE_DIR, f'{cid}_latency.txt'), 'r') as stdin:
        data = json.load(stdin)
    if "starttransfer_time" in data.keys():
        resolve_time = data["starttransfer_time"]
        if "total_time" in data.keys():
            download_time = str(float(data["total_time"]) - float(resolve_time))
    return resolve_time, download_time


def analyse_content_provider(all_block_provider_dic, cid):
    """
    Parse the content provider for a particular content (cid)
    :param all_block_provider_dic: dictionary contains {block_cid : providerID}
    :param cid: cid of the object
    :return: list of provider for the cid
    """
    # append root block provider
    logging.info(f'Analyze Storage CID {cid}')
    try:
        actual_provider = [all_block_provider_dic[cid]]
    except KeyError:
        # case when there is no actual provider
        logging.info(f'Content CID {cid} non reachable')
        actual_provider = []
        return actual_provider
    # read sub blocks provider
    process = subprocess.Popen(
        ['./ipfs', 'ls', cid],
        stdout=subprocess.PIPE)
    try:
        r_code = process.wait(timeout=300)
        if r_code != 0:
            logging.info(f"Error on IPFS LS with CID {cid} and exit code {r_code}")
    except subprocess.TimeoutExpired:
        logging.info(f'IPFS ls Timeout with CID {cid}')
    for line in process.stdout.readlines():
        line = line.decode('utf-8')
        line = line.split(" ")
        # get block cid
        block_cid = line[0]
        provider = all_block_provider_dic[block_cid]
        # add provider if not in list
        if provider not in actual_provider:
            actual_provider.append(provider)
            logging.info(f'CID {cid} adding new provider {provider}')

    return actual_provider


def get_ip_hop(address: Address):
    """
    find ip hop value from given Address
    :param address: Address object
    :return: None
    """
    if address.ip_type == 'ip6' or address.protocol == 'dns':
        return
        # try to use traceroute to get rtt
    if address.protocol == 'tcp':
        protocol = "-T"
    else:
        protocol = '-U'
    # error checking in case of domain:
    try:
        ipaddress.ip_address(address.ip)
    except Exception as e:
        logging.info(e)
        return
    # try traceroute
    logging.info(f'Start Traceroute {address.ip}')
    process = subprocess.Popen(
        ['sudo', 'traceroute', address.ip, protocol, '-p', address.port, '-m', '20'],
        stdout=subprocess.PIPE)

    try:
        process.wait(300)
        line = process.stdout.readlines()[-1]
        line = line.decode('utf-8')
        line = line.replace("\n", "")
        line = line.lstrip()
        logging.info(line)
        address.ip_hop = line.split(" ")[0]
    except subprocess.TimeoutExpired as e:
        logging.info(f'Traceroute timeout {address.ip}')
        process.kill()
    except Exception as e:
        logging.error(f'Traceroute Error {e}')


def get_rtt(address: Address):
    """
    find rtt value from given Address
    :param address: Address object
    :return: None
    """
    if address.ip_type == 'ip6':
        return
    try:
        logging.info(f'Start RTT {address.__dict__}')
        host = icmplib.ping(address.ip, count=5, interval=0.2, privileged=True)
    except Exception as e:
        print(e)
        return
    if host.is_alive:
        address.rtt = host.avg_rtt
        logging.info(host.rtts)
    else:
        return
        # try to use traceroute to get rtt
        # logging.info(f'Start RTT by traceroute {address.ip}')
        # process = subprocess.Popen(
        #     ['sudo', 'traceroute', address.ip, '-T', '-p', address.port, '-m', '100'],
        #     stdout=subprocess.PIPE)
        # line = process.stdout.readlines()[-1]
        # try:
        #     line = line.decode('utf-8')
        #     line = line.replace("\n", "")
        #     line = line.split(" ")
        #     rtt = float(line[line.index("ms") - 1])
        #     address.rtt = str(rtt)
        #     logging.info(f'RTT {address.ip} {rtt}')
        # except Exception:
        #     logging.error(line)


def get_peer_ip(result_host_dic: dict):
    """
    find peer multi address based on peerID
    :param result_host_dic: [provider_peerID : who provides (peerID)]
    :return: dic {provider_peerID : Address[]}
    """
    provider_ip = {}
    for peer in result_host_dic.keys():
        process = subprocess.Popen(['./ipfs', 'dht', 'findpeer', peer], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        try:
            r_code = process.wait(timeout=300)
            if r_code != 0:
                logging.info(f"Error on IPFS findpeer with Peer {peer} and exit code {r_code}")
                for line in process.stderr.readlines():
                    logging.info(line)
                for line in process.stdout.readlines():
                    logging.info(line)
                provider_ip[peer] = []
                return provider_ip
            # case of no route find
            for line in process.stderr.readlines():
                if 'Error' in str(line):
                    logging.info(f"Error on IPFS findpeer with Peer {peer} output {str(line)}")
                    provider_ip[peer] = []
                    return provider_ip
            provider_ip[peer] = []
            with open(os.path.join(SAVE_DIR, f'{peer}_ip.txt'), 'w+') as stdout:
                for line in process.stdout.readlines():
                    line = line.decode('utf-8')
                    # store all peer ip
                    stdout.write(line)
                    line = line.replace("\n", "")
                    line = line.split("/")
                    ip_type = line[1]
                    ip_value = line[2]
                    protocol = line[3]
                    port = line[4]
                    if ip_type == 'ip6' and ip_value == '::1':
                        # local v6 ignore
                        continue
                    elif ip_type == 'ip4':
                        # exclude private ip address
                        if ipaddress.ip_address(ip_value) in ipaddress.IPv4Network('10.0.0.0/8') or \
                                ipaddress.ip_address(ip_value) in ipaddress.IPv4Network('172.16.0.0/12') or \
                                ipaddress.ip_address(ip_value) in ipaddress.IPv4Network('127.0.0.0/8') or \
                                ipaddress.ip_address(ip_value) in ipaddress.IPv4Network('192.168.0.0/16'):
                            continue
                    # add valid ip address info
                    logging.info(f'Peer {peer} has external IP {ip_value}:{port}, {ip_type}, {protocol}')
                    if peer not in provider_ip.keys():
                        provider_ip[peer] = []
                    address = Address(ip_value, ip_type, port, protocol)
                    provider_ip[peer].append(address)
        except subprocess.TimeoutExpired as e:
            logging.info(f"Timeout for {peer}")
    return provider_ip


def ips_find_provider(cid):
    """
    call ipfs to find provider for cid specified, and do a DHT dump before finding
    :param cid: cid to find
    :return: None
    """

    with open(os.path.join(SAVE_DIR, f'{cid}_dht.txt'), 'w') as stdout:
        stdout.flush()
        try:
            process = subprocess.Popen(['./ipfs', 'stats', 'dht'], stdout=stdout)
            r_code = process.wait(timeout=300)
            if r_code != 0:
                logging.info(f"Error on IPFS stats dht with CID {cid} and exit code {r_code}")
        except subprocess.TimeoutExpired:
            process.kill()

    with open(os.path.join(SAVE_DIR, f'{cid}_provid.txt'), 'w') as stdout:
        stdout.flush()
        try:
            process = subprocess.Popen(['./ipfs', 'dht', 'findprovs', '-v', cid], stdout=stdout)
            r_code = process.wait(timeout=300)
            if r_code != 0:
                logging.info(f"Error on IPFS dht findprovs with CID {cid} and exit code {r_code}")
        except subprocess.TimeoutExpired:
            process.kill()
            logging.info(f'CID {cid} findprov timeout')


def get_storage_info(cid):
    """
    Get the number of blocks and the size of the conten given the CID
    :param cid: cid to find
    :return: None
    """

    with open(os.path.join(SAVE_DIR, f'{cid}_storage.txt'), 'w') as stdout:
        stdout.flush()
        try:
            process = subprocess.Popen(['./ipfs', 'dag', 'stat', cid], stdout=stdout)
            r_code = process.wait(timeout=300)
            if r_code != 0:
                logging.info(f"Error on IPFS dag stat with CID {cid} and exit code {r_code}")
        except subprocess.TimeoutExpired:
            logging.info(f'CID {cid} storage timeout')
            process.kill()


def get_latency_info(cid):
    """
    Get resolve time and download time
    :param cid: cid to find
    :return: None
    """

    with open(os.path.join(SAVE_DIR, f'{cid}_latency.txt'), 'w') as stdout:
        stdout.flush()
        try:
            process = subprocess.Popen(['./ipfs', 'get', cid, "-o", SAVE_DIR], stdout=stdout)
            r_code = process.wait(timeout=600)
            if r_code != 0:
                logging.info(f"Error on IPFS get with CID {cid} and exit code {r_code}")
        except subprocess.TimeoutExpired:
            process.kill()
            logging.info(f'CID {cid} download timeout')


def get_latency_info_gateway(cid):
    """
    Get resolve and download time via ipfs getway
    :param cid: cid to find
    :return: None
    """
    # remove possible cache
    # os.system(f"ipfs block rm $(ipfs ls --size=false {cid})")
    # time.sleep(5)
    logging.info(f"Staring gc {cid}")
    cmd = f"./ipfs block rm $(./ipfs ls --size=false {cid})"
    process = subprocess.Popen(cmd,
                               shell=True,
                               preexec_fn=os.setsid,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    logging.info(process.args)
    # for line in process.stdout.readlines():
    #     logging.info(f'Repo GCed {line.decode("utf-8")}')
    # for line in process.stderr.readlines():
    #     logging.info(f'Error {line.decode("utf-8")}')
    try:
        outs, errs = process.communicate(timeout=90)
        logging.info(f'Done {outs.decode("utf-8")})')
        logging.info(f'Error {errs.decode("utf-8")}')
        # if rcode != 0:
        #     logging.info(f'Error exit code {rcode}')
    except subprocess.TimeoutExpired:
        logging.info(f'Repo GC {cid} Timeout')
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        # process.kill()
        # outs, errs = process.communicate()
    try:
        file_size = 0
        t = multiprocessing.Process(target=get_video, args=(cid,))
        t.start()
        prv_time = time.time()
        while t.is_alive():
            time.sleep(5)
            current_size = os.path.getsize(os.path.join(SAVE_DIR, cid))
            logging.info(f"Current_size {current_size}")
            current_time = time.time()
            if current_size != file_size:
                file_size = current_size
                prv_time = current_time
            elif (current_time - prv_time) > 300:
                # case we have no progress over 5 min we consider dead
                logging.info(f"Collect Video Timeout {cid}")
                t.terminate()
                t.join()
                exit(-1)
            else:
                # check every minute
                time.sleep(60)
        t.terminate()
        t.join()
    except Exception as e:
        logging.info(f"Join error {e}")

def get_video(cid):
    with open(os.path.join(SAVE_DIR, f'{cid}'), 'wb') as vid_out:
        try:
            url = f"http://127.0.0.1:8080/ipfs/{cid}"
            #    url = "http://gateway.ipfs.io/ipfs/" + cid
            logging.info("Accessing URL %s", url)
            c = pycurl.Curl()
            c.setopt(c.URL, url)
            c.setopt(c.VERBOSE, False)
            c.setopt(c.WRITEDATA, vid_out)
            c.setopt(c.FOLLOWLOCATION, 1)
            c.setopt(c.CONNECTTIMEOUT, 300)
            c.perform()

            """
            curl_easy_perform()
            |
            |--NAMELOOKUP
            |--|--CONNECT
            |--|--|--APPCONNECT
            |--|--|--|--PRETRANSFER
            |--|--|--|--|--STARTTRANSFER
            |--|--|--|--|--|--TOTAL
            |--|--|--|--|--|--REDIRECT
            """
            m = {"total_time": c.getinfo(pycurl.TOTAL_TIME), "namelookup_time": c.getinfo(pycurl.NAMELOOKUP_TIME),
                 "connect_time": c.getinfo(pycurl.CONNECT_TIME), "pretransfer_time": c.getinfo(pycurl.PRETRANSFER_TIME),
                 "redirect_time": c.getinfo(pycurl.REDIRECT_TIME),
                 "starttransfer_time": c.getinfo(pycurl.STARTTRANSFER_TIME),
                 "length": c.getinfo(pycurl.CONTENT_LENGTH_DOWNLOAD)}
            # in bytes

            logging.info(f"Got metric for CID {cid}, {m}")
            with open(os.path.join(SAVE_DIR, f'{cid}_latency.txt'), 'w') as stdout:
                json.dump(m, stdout)
        except Exception as e:
            logging.info(e)
            with open(os.path.join(SAVE_DIR, f'{cid}_latency.txt'), 'w') as stdout:
                pass

        # get cached performance
        try:
            url = f"http://127.0.0.1:8080/ipfs/{cid}"
            #    url = "http://gateway.ipfs.io/ipfs/" + cid
            logging.info("Accessing URL %s", url)
            c = pycurl.Curl()
            c.setopt(c.URL, url)
            c.setopt(c.VERBOSE, False)
            c.setopt(c.WRITEDATA, vid_out)
            c.setopt(c.FOLLOWLOCATION, 1)
            c.setopt(c.CONNECTTIMEOUT, 300)
            c.perform()

            """
            curl_easy_perform()
            |
            |--NAMELOOKUP
            |--|--CONNECT
            |--|--|--APPCONNECT
            |--|--|--|--PRETRANSFER
            |--|--|--|--|--STARTTRANSFER
            |--|--|--|--|--|--TOTAL
            |--|--|--|--|--|--REDIRECT
            """
            m = {"total_time": c.getinfo(pycurl.TOTAL_TIME), "namelookup_time": c.getinfo(pycurl.NAMELOOKUP_TIME),
                 "connect_time": c.getinfo(pycurl.CONNECT_TIME), "pretransfer_time": c.getinfo(pycurl.PRETRANSFER_TIME),
                 "redirect_time": c.getinfo(pycurl.REDIRECT_TIME),
                 "starttransfer_time": c.getinfo(pycurl.STARTTRANSFER_TIME),
                 "length": c.getinfo(pycurl.CONTENT_LENGTH_DOWNLOAD)}
            # in bytes
            logging.info(f"Got metric for CID {cid}, {m}")
            with open(os.path.join(SAVE_DIR, f'{cid}_latency_cached.txt'), 'w') as stdout:
                json.dump(m, stdout)
        except Exception as e:
            logging.info(e)
            with open(os.path.join(SAVE_DIR, f'{cid}_latency_cached.txt'), 'w') as stdout:
                pass
def preprocess_file(cid):
    """
    preprocess cid files,i.e. get the file, providers, etc
    :param cid: cid of the file
    :return:
    """
    logging.info(f'Loading CID {cid}')
    if os.path.exists(os.path.join(SAVE_DIR, f'{cid}_summary.json')):
        exit(0)
    ips_find_provider(cid)
    get_latency_info_gateway(cid)
    get_storage_info(cid)


def postprocess_file(cid, all_provider_dic, all_block_provider_dic):
    """
    postprocess cid files, i.e ipfs hop, ip hop, rtt, ip etc
    :param all_block_provider_dic: dic contains block -> provider
    :param all_provider_dic: dic contains cid -> {hosts : provider}
    :param cid: cid of the file
    :return: Stats
    """
    logging.info(f'Analyzing CID {cid}')
    _, ipfs_hop = analyse_ipfs_hops(cid, all_provider_dic[cid])
    logging.info(f'CID {cid} ipfs hop {ipfs_hop}')
    num_blocks, content_size = analyse_storage(cid)
    logging.info(f'CID {cid} #blocks {num_blocks}, size {content_size}')
    resolve_time, download_time = analyse_latency_gateway(cid)
    logging.info(f'CID {cid} #r_time {resolve_time}, d_time {download_time}')
    if num_blocks != -1 and content_size != 0 and ipfs_hop != -1:
        actual_provider = analyse_content_provider(all_block_provider_dic, cid)
    else:
        actual_provider = []
    logging.info(f'CID {cid} actual provider {actual_provider}')
    if ipfs_hop == -1:
        # case of no result find
        logging.info(f'NO IPFS INFO FOUND CID {cid}')
        # stats = Stats(cid, ipfs_hop, {}, None, None, None, None, None)
        # all_stats.append(stats)
        # continue
    # add actual provider if not in the providers list
    # for p in actual_provider:
    #     if p not in all_provider_dic[cid].keys():
    #         logging.info(f'Adding actual provider {p} to dic')
    #         all_provider_dic[cid][p] = ""
    logging.info(f'CID {cid} getting peer IP values')
    providers_ips = get_peer_ip(all_provider_dic[cid])
    logging.info(f'CID {cid} getting actual peer IP values')
    actual_provider_dic = {provider: "None" for provider in actual_provider}
    logging.info(f'CID {cid} actual provider dic {actual_provider_dic}')
    actual_provider_ips = get_peer_ip(actual_provider_dic)
    stats = Stats(cid, ipfs_hop, providers_ips, num_blocks, content_size,
                  resolve_time, download_time, actual_provider_ips)
    logging.info(f'CID {cid} getting peer RTT and IP hop info')
    for peer in providers_ips.keys():
        for address in providers_ips[peer]:
            get_rtt(address)
            get_ip_hop(address)
            logging.info(f'Address {address.__dict__}')

    logging.info(f'CID {cid} getting actual peer RTT and IP hop info')
    for peer in actual_provider_ips.keys():
        for address in actual_provider_ips[peer]:
            get_rtt(address)
            get_ip_hop(address)
            logging.info(f'Address {address.__dict__}')
    # save progress
    logging.info(f'Saving Progress CID {cid}')
    with open(os.path.join(SAVE_DIR, f'{cid}_progress.txt'), 'a') as fout:
        json.dump(copy.copy(stats), fout, cls=StatsEncoder)
        fout.write('\n')

    return stats


def clear_ipfs_repo():
    """
    Repo GC before collecting data
    :return:
    """
    logging.info("Staring repo gc")
    process = subprocess.Popen(['./ipfs', 'repo', 'gc'], stdout=subprocess.PIPE)
    for line in process.stdout.readlines():
        logging.info(f'Repo GCed {line}')
    try:
        rcode = process.wait(timeout=300)
        if rcode != 0:
            logging.info(f'Error exit code {rcode}')
    except subprocess.TimeoutExpired:
        logging.info(f'Repo GC Timeout')
        process.kill()


def main(cid, dir_name, daemon_file):
    # repo gc
    # clear_ipfs_repo()
    # start preprocess with multi threading

    preprocess_file(cid)
    # read daemon log file
    all_provider_dic = {}  # {cid : result_host_dic={}}
    all_block_provider_dic = {}  # {block_cid, provider_ID}
    target_block_found = False
    # shutil.copyfile(daemon_file, os.path.join(SAVE_DIR, "daemon.txt"))
    with open(daemon_file, 'r') as stdin:
        for line in stdin:
            # read block provider information
            if "bitswap.go" in line and "Block" in line and "from" in line:
                index = line.find("Block")
                line = line.replace("\n", "")
                line = line[index:]
                line = line.split(' ')
                # Block bafkreicp3z76wlf2bx3zmwbjzgqpsdvkb4coxuruj4fyq5w7gpvo2tfiuq
                # recived from 12D3KooWGBWx9gyUFTVQcKMTenQMSyE2ad9m7c9fpjS4NMjoDien
                current_cid = line[1].split('\n')[0]
                provider_id = line[-1]
                # logging.info(f'Block {current_cid} provider {provider_id}')
                if current_cid == cid:
                    target_block_found = True
                if target_block_found:
                    all_block_provider_dic[current_cid] = provider_id
                continue
            # read findprovs output info
            if "routing.go" not in line or "":
                continue
            index = line.find("cid")
            line = line.replace("\n", "")
            line = line[index:]
            line = line.split(" ")
            c = line[1]

            # case where cid is not root cid we asked for
            # TODO maybe this caused by block cid finding ?
            if c != cid:
                # logging.info(f'CID {cid} not in sample files')
                continue
            logging.info(f'CID {c} has providerID {line[5]}; NodeID {line[3]}')
            # add valid cid in to dic
            # "cid %s provider %s provides %s",oriKey, p, prov.ID
            if c not in all_provider_dic.keys():
                result_host_dic = {}
                all_provider_dic[cid] = result_host_dic
            else:
                result_host_dic = all_provider_dic[cid]
            result_host_dic[line[5]] = line[3]
    logging.info(f'all_provider_dic = {all_provider_dic}')
    logging.info(f'all_block_provider_dic = {all_block_provider_dic}')

    # star multi-threading for post process
    stat = postprocess_file(cid, all_provider_dic, all_block_provider_dic)
    save_path = os.path.join(dir_name, f'{cid}_summary.json')
    # write to file
    with open(save_path, 'w') as fout:
        json.dump(stat, fout, cls=StatsEncoder)


if __name__ == '__main__':
    # setup parser
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', type=str, help="daemon file log name", required=True)
    parser.add_argument('-d', '--directory', type=str, help="input directory name", required=True)
    parser.add_argument('-c', '--cid', type=str, help="cid", required=True)
    args = parser.parse_args()
    # setup logger
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s',
                        level=logging.INFO,
                        datefmt='%Y-%m-%d %H:%M:%S',
                        filename=os.path.join(args.directory, 'record.log'))  # stream=sys.stdout
    SAVE_DIR = args.directory
    logging.info(f'dir_name = {SAVE_DIR}\n'
                 f'cid = {args.cid}\n'
                 f'daemon_file = {args.file}')

    # prefix = "/out/videos"
    main(args.cid, args.directory, args.file)
