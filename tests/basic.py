"""
Basic protocol and dataplane test cases

It is recommended that these definitions be kept in their own
namespace as different groups of tests will likely define 
similar identifiers.

Current Assumptions:

  The switch is actively attempting to contact the controller at the address
indicated in oftest.config.

"""

import time
import sys
import logging

import unittest
import random

from oftest import config
import oftest.controller as controller
import oftest.dataplane as dataplane
import oftest.base_tests as base_tests
import ofp

import oftest.illegal_message as illegal_message

from oftest.testutils import *

TEST_VID_DEFAULT = 2

@group('smoke')
class Echo(base_tests.SimpleProtocol):
    """
    Test echo response with no data
    """
    def runTest(self):
        request = ofp.message.echo_request()
        response, pkt = self.controller.transact(request)
        self.assertTrue(response is not None,
                        "Did not get echo reply")
        self.assertEqual(response.type, ofp.OFPT_ECHO_REPLY,
                         'response is not echo_reply')
        self.assertEqual(request.xid, response.xid,
                         'response xid != request xid')
        self.assertEqual(len(response.data), 0, 'response data non-empty')

class EchoWithData(base_tests.SimpleProtocol):
    """
    Test echo response with short string data
    """
    def runTest(self):
        request = ofp.message.echo_request(data='OpenFlow Will Rule The World')
        response, pkt = self.controller.transact(request)
        self.assertTrue(response is not None,
                        "Did not get echo reply (with data)")
        self.assertEqual(response.type, ofp.OFPT_ECHO_REPLY,
                         'response is not echo_reply')
        self.assertEqual(request.xid, response.xid,
                         'response xid != request xid')
        self.assertEqual(request.data, response.data,
                         'response data does not match request')


class PacketInBroadcastCheck(base_tests.SimpleDataPlane):
    """
    Check if bcast pkts leak when no flows are present

    Clear the flow table
    Send in a broadcast pkt
    Look for the packet on other dataplane ports.
    """

    def runTest(self):
        # Need at least two ports
        self.assertTrue(len(config["port_map"]) > 1, "Too few ports for test")

        delete_all_flows(self.controller)
        do_barrier(self.controller)

        of_ports = config["port_map"].keys()
        d_port = of_ports[0]
        pkt = simple_eth_packet(eth_dst='ff:ff:ff:ff:ff:ff')

        logging.info("BCast Leak Test, send to port %s" % d_port)
        self.dataplane.send(d_port, str(pkt))

        (of_port, pkt_in, pkt_time) = self.dataplane.poll(exp_pkt=pkt)
        self.assertTrue(pkt_in is None,
                        'BCast packet received on port ' + str(of_port))


class FlowStatsGet(base_tests.SimpleProtocol):
    """
    Get stats 

    Simply verify stats get transaction
    """

    def runTest(self):
        logging.info("Running StatsGet")
        logging.info("Inserting trial flow")
        request = flow_mod_gen(config["port_map"], True)
        self.controller.message_send(request)
        
        logging.info("Sending flow request")
        request = ofp.message.flow_stats_request(out_port=ofp.OFPP_NONE,
                                             table_id=0xff)
        request.match.wildcards = 0 # ofp.OFPFW_ALL
        response, pkt = self.controller.transact(request)
        self.assertTrue(response is not None,
                        "Did not get response for flow stats")
        logging.debug(response.show())

class TableStatsGet(base_tests.SimpleProtocol):
    """
    Get table stats 

    Simply verify table stats get transaction
    """
    def runTest(self):
        logging.info("Running TableStatsGet")
        logging.info("Inserting trial flow")
        request = flow_mod_gen(config["port_map"], True)
        self.controller.message_send(request)
        
        logging.info("Sending table stats request")
        request = ofp.message.table_stats_request()
        response, pkt = self.controller.transact(request)
        self.assertTrue(response is not None,
                        "Did not get reply for table stats")
        logging.debug(response.show())

class DescStatsGet(base_tests.SimpleProtocol):
    """
    Get stats 

    Simply verify stats get transaction
    """
    def runTest(self):
        logging.info("Running DescStatsGet")
        
        logging.info("Sending stats request")
        request = ofp.message.desc_stats_request()
        response, pkt = self.controller.transact(request)
        self.assertTrue(response is not None,
                        "Did not get reply for desc stats")
        logging.debug(response.show())

class FlowMod(base_tests.SimpleProtocol):
    """
    Insert a flow

    Simple verification of a flow mod transaction
    """

    def runTest(self):
        logging.info("Running " + str(self))
        request = flow_mod_gen(config["port_map"], True)
        self.controller.message_send(request)

@group('smoke')
class PortConfigMod(base_tests.SimpleProtocol):
    """
    Modify a bit in port config and verify changed

    Get the switch configuration, modify the port configuration
    and write it back; get the config again and verify changed.
    Then set it back to the way it was.
    """

    def runTest(self):
        logging.info("Running " + str(self))
        for of_port, ifname in config["port_map"].items(): # Grab first port
            break

        (hw_addr, port_config, advert) = \
            port_config_get(self.controller, of_port)
        self.assertTrue(port_config is not None, "Did not get port config")

        logging.debug("No flood bit port " + str(of_port) + " is now " + 
                           str(port_config & ofp.OFPPC_NO_FLOOD))

        rv = port_config_set(self.controller, of_port,
                             port_config ^ ofp.OFPPC_NO_FLOOD, ofp.OFPPC_NO_FLOOD)
        self.assertTrue(rv != -1, "Error sending port mod")
        do_barrier(self.controller)

        # Verify change took place with same feature request
        (hw_addr, port_config2, advert) = \
            port_config_get(self.controller, of_port)
        logging.debug("No flood bit port " + str(of_port) + " is now " + 
                           str(port_config2 & ofp.OFPPC_NO_FLOOD))
        self.assertTrue(port_config2 is not None, "Did not get port config2")
        self.assertTrue(port_config2 & ofp.OFPPC_NO_FLOOD !=
                        port_config & ofp.OFPPC_NO_FLOOD,
                        "Bit change did not take")
        # Set it back
        rv = port_config_set(self.controller, of_port, port_config,
                             ofp.OFPPC_NO_FLOOD)
        self.assertTrue(rv != -1, "Error sending port mod")
        do_barrier(self.controller)

class PortConfigModErr(base_tests.SimpleProtocol):
    """
    Modify a bit in port config on an invalid port and verify
    error message is received.
    """

    def runTest(self):
        logging.info("Running " + str(self))

        # pick a random bad port number
        bad_port = random.randint(1, ofp.OFPP_MAX)
        count = 0
        while (count < 50) and (bad_port in config["port_map"].keys()):
            bad_port = random.randint(1, ofp.OFPP_MAX)
            count = count + 1
        self.assertTrue(count < 50, "Error selecting bad port")
        logging.info("Select " + str(bad_port) + " as invalid port")

        rv = port_config_set(self.controller, bad_port,
                             ofp.OFPPC_NO_FLOOD, ofp.OFPPC_NO_FLOOD)
        self.assertTrue(rv != -1, "Error sending port mod")

        # poll for error message
        while True:
            (response, raw) = self.controller.poll(ofp.OFPT_ERROR)
            if not response:  # Timeout
                break
            if response.code == ofp.OFPPMFC_BAD_PORT:
                logging.info("Received error message with OFPPMFC_BAD_PORT code")
                break
            if not config["relax"]:  # Only one attempt to match
                break
            count += 1
            if count > 10:   # Too many tries
                break

        self.assertTrue(response is not None, 'Did not receive error message')

@group('smoke')
class BadMessage(base_tests.SimpleProtocol):
    """
    Send a message with a bad type and verify an error is returned
    """

    def runTest(self):
        logging.info("Running " + str(self))
        request = illegal_message.illegal_message_type()

        reply, pkt = self.controller.transact(request)
        logging.info(repr(pkt))
        self.assertTrue(reply is not None, "Did not get response to bad req")
        self.assertTrue(reply.type == ofp.OFPT_ERROR,
                        "reply not an error message")
        logging.info(reply.err_type)
        self.assertTrue(reply.err_type == ofp.OFPET_BAD_REQUEST,
                        "reply error type is not bad request")
        self.assertTrue(reply.code == ofp.OFPBRC_BAD_TYPE,
                        "reply error code is not bad type")

@group('smoke')
@version('1.1+')
class TableModConfig(base_tests.SimpleProtocol):
    """
    Simple table modification

    Mostly to make sure the switch correctly responds to these messages.
    More complicated tests in the multi-tables.py tests
    """
    def runTest(self):
        # First table should always exist
        table_id = 0

        def get_table_config():
            request = ofp.message.table_stats_request()
            response, _ = self.controller.transact(request)
            try:
                table_stats = [x for x in response.entries if x.table_id == table_id][0]
            except IndexError:
                raise AssertionError("table id %d not found" % table_id)
            return table_stats.config

        # Get current configuration
        orig_table_config = get_table_config()

        # Change the configuration
        if orig_table_config == ofp.OFPTC_TABLE_MISS_CONTROLLER:
            new_table_config = ofp.OFPTC_TABLE_MISS_DROP
        else:
            new_table_config = ofp.OFPTC_TABLE_MISS_CONTROLLER
        request = ofp.message.table_mod(table_id=table_id, config=new_table_config)
        self.controller.message_send(request)
        self.controller.transact(ofp.message.barrier_request())

        # Check the configuration took
        self.assertEqual(get_table_config(), new_table_config)

        # Change the configuration back
        request = ofp.message.table_mod(table_id=table_id, config=orig_table_config)
        self.controller.message_send(request)
        self.controller.transact(ofp.message.barrier_request())

if __name__ == "__main__":
    print "Please run through oft script:  ./oft --test_spec=basic"
