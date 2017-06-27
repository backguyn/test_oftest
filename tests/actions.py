
"""These tests fall under Conformance Test-Suite (OF-SWITCH-1.0.0 TestCases).
    Refer Documentation -- Detailed testing methodology 
    <Some of test-cases are directly taken from oftest> """

"Test Suite 6  ---> Actions "


import logging

import unittest
import random
import time

from oftest import config
import oftest.controller as controller
import ofp
import oftest.dataplane as dataplane
import oftest.parse as parse
import oftest.base_tests as base_tests

from oftest.testutils import *
from time import sleep
from FuncUtils import *

class NoAction(base_tests.SimpleDataPlane):

    """NoActionDrop : no action added to flow , drops the packet."""

    def runTest(self):
        
        logging.info("Running No_Action test")

        of_ports = config["port_map"].keys()
        of_ports.sort()
        self.assertTrue(len(of_ports) > 1, "Not enough ports for test")
        
        #Clear switch state
        delete_all_flows(self.controller)
        
        logging.info("Install a flow without action")
        logging.info("Send packets matching that flow")
        logging.info("Expecting switch to drop all packets")

        # Insert a flow wildcard all without any action 
        pkt = simple_tcp_packet()
        match = parse.packet_to_flow_match(pkt)
        self.assertTrue(match is not None, "Could not generate flow match from pkt")
        match.wildcards=ofp.OFPFW_ALL
        match.in_port = of_ports[0]
        
        msg = ofp.message.flow_add()
        msg.out_port = ofp.OFPP_NONE
        msg.buffer_id = 0xffffffff
        msg.match = match
        self.controller.message_send(msg)
        do_barrier(self.controller)

        #Sending N packets matching the flow inserted
        for pkt_cnt in range(5):
            self.dataplane.send(of_ports[0],str(pkt))
        
        #Verify packets not recieved on any of the dataplane ports 
        (rcv_port, rcv_pkt, pkt_time) = self.dataplane.poll(timeout=1,exp_pkt=pkt)
        self.assertTrue(rcv_pkt is None,
                "Packet received on port " + str(rcv_port))

        #Verify packets not sent on control plane either
        verify_no_packet_in(self, str(pkt), of_ports[0])


class Announcement(base_tests.SimpleDataPlane):
    
    """Announcement : Get all supported actions by the switch.
    Send OFPT_FEATURES_REQUEST to get features supported by sw."""

    def runTest(self):

        logging.info("Running Announcement test")

        logging.info("Sending Features_Request")
        logging.info("Expecting Features Reply with supported actions")

        # Sending Features_Request
        request = ofp.message.features_request()
        (reply, pkt) = self.controller.transact(request)
        self.assertTrue(reply is not None, "Failed to get any reply")
        self.assertEqual(reply.type, ofp.OFPT_FEATURES_REPLY,'Response is not Features_reply')
        
        supported_actions =[]
        if(reply.actions &1<<ofp.OFPAT_OUTPUT):
            supported_actions.append('OFPAT_OUTPUT')
        if(reply.actions &1<<ofp.OFPAT_SET_VLAN_VID):
            supported_actions.append('OFPAT_SET_VLAN_VID')
        if(reply.actions &1<<ofp.OFPAT_SET_VLAN_PCP):
            supported_actions.append('OFPAT_SET_VLAN_PCP')
        if(reply.actions &1<<ofp.OFPAT_STRIP_VLAN):
            supported_actions.append('OFPAT_STRIP_VLAN')
        if(reply.actions &1<<ofp.OFPAT_SET_DL_SRC):
            supported_actions.append('OFPAT_SET_DL_SRC')
        if(reply.actions &1<<ofp.OFPAT_SET_DL_DST):
            supported_actions.append('OFPAT_SET_NW_SRC')
        if(reply.actions &1<<ofp.OFPAT_SET_NW_DST):
            supported_actions.append('OFPAT_SET_NW_DST')
        if(reply.actions &1<<ofp.OFPAT_SET_NW_TOS):
            supported_actions.append('OFPAT_SET_NW_TOS')
        if(reply.actions &1<<ofp.OFPAT_SET_TP_SRC):
            supported_actions.append('OFPAT_SET_TP_SRC')
        if(reply.actions &1<<ofp.OFPAT_SET_TP_DST):
            supported_actions.append('OFPAT_SET_TP_DST')
        if(reply.actions &1<<ofp.OFPAT_EXPERIMENTER):
            supported_actions.append('OFPAT_EXPERIMENTER')
        if(reply.actions &1<<ofp.OFPAT_ENQUEUE):
            supported_actions.append('OFPAT_ENQUEUE')
        
        logging.info(supported_actions)
        

class ForwardLocal(base_tests.SimpleDataPlane):
   
    """ForwardLocal : Packet is sent to  OFPP_LOCAL port . 
        TBD : To verify packet recieved in the local networking stack of switch"""

    def runTest(self):

        logging.info("Running Forward_Local test")

        of_ports = config["port_map"].keys()
        of_ports.sort()
        self.assertTrue(len(of_ports) > 1, "Not enough ports for test")
        
        #Clear switch state
        delete_all_flows(self.controller)
        
        logging.info("Insert a flow with output action port OFPP_LOCAL")
        logging.info("Send packet matching the flow")
        logging.info("Expecting packet in the local networking stack of switch")
        
        #Clear switch state
        pkt = simple_tcp_packet()
        match = parse.packet_to_flow_match(pkt)
        act = ofp.action.output()

        for ingress_port in of_ports:
            #Delete the flows
            delete_all_flows(self.controller)

            match.in_port = ingress_port
            #Create flow mod message
            request = ofp.message.flow_add()
            request.match = match
            act.port = ofp.OFPP_LOCAL
            request.actions.append(act)

            logging.info("Inserting flow")
            self.controller.message_send(request)
            do_barrier(self.controller)

            #Send packet matching the flow
            logging.info("Sending packet to dp port " + str(ingress_port))
            self.dataplane.send(ingress_port, str(pkt))

            #TBD: Verification of packets being recieved.


class AddVlanTag(base_tests.SimpleDataPlane):
    
    """AddVlanTag : Adds VLAN Tag to untagged packet."""

    def runTest(self):

        logging.info("Running Add_vlan_tag test")

        of_ports = config["port_map"].keys()
        of_ports.sort()
        self.assertTrue(len(of_ports) > 1, "Not enough ports for test")
        
        #Clear switch state
        delete_all_flows(self.controller)

        logging.info("Verify if switch supports the action -- set vlan id, if not skip the test")
        logging.info("Insert a flow with set vid action")
        logging.info("Send packet matching the flow , verify recieved packet has vid set")
        
        #Verify set_vlan_id is a supported action
        sup_acts = sw_supported_actions(self)
        if not(sup_acts & 1<<ofp.OFPAT_SET_VLAN_VID):
           skip_message_emit(self, "Add VLAN tag test skipped")
           return
        
        #Create packet to be sent and an expected packet with vid set
        new_vid = 2
        len_wo_vid = 100
        len_w_vid = 104
        pkt = simple_tcp_packet(pktlen=len_wo_vid)
        exp_pkt = simple_tcp_packet(pktlen=len_w_vid, dl_vlan_enable=True, 
                                    vlan_vid=new_vid,vlan_pcp=0)
        vid_act = ofp.action.set_vlan_vid()
        vid_act.vlan_vid = new_vid

        #Insert flow with action -- set vid , Send packet matching the flow, Verify recieved packet is expected packet
        wildcards = ofp.OFPFW_ALL ^ ofp.OFPFW_IN_PORT ^ ofp.OFPFW_DL_SRC ^ ofp.OFPFW_DL_DST ^ ofp.OFPFW_DL_TYPE ^ ofp.OFPFW_NW_SRC_ALL ^ ofp.OFPFW_NW_DST_ALL
        flow_match_test(self, config["port_map"], pkt=pkt, wildcards=wildcards,
                        exp_pkt=exp_pkt, action_list=[vid_act])

class ModifyVlanTag(base_tests.SimpleDataPlane):

    """ModifyVlanTag : Modifies VLAN Tag to tagged packet."""
    
    def runTest(self):

        logging.info("Running Modify_Vlan_Tag test")

        of_ports = config["port_map"].keys()
        of_ports.sort()
        self.assertTrue(len(of_ports) > 1, "Not enough ports for test")
        
        #Clear switch state
        delete_all_flows(self.controller)

        logging.info("Verify if switch supports the action -- modify vlan id, if not skip the test")
        logging.info("Insert a flow with action --set vid ")
        logging.info("Send tagged packet matching the flow , verify recieved packet has vid rewritten")
        
        #Verify set_vlan_id is a supported action
        sup_acts = sw_supported_actions(self)
        if not (sup_acts & 1 << ofp.OFPAT_SET_VLAN_VID):
            skip_message_emit(self, "Modify VLAN tag test skipped")
            return

        #Create a tagged packet with old_vid to be sent, and expected packet with new_vid
        old_vid = 2
        new_vid = 3
        pkt = simple_tcp_packet(dl_vlan_enable=True, vlan_vid=old_vid)
        exp_pkt = simple_tcp_packet(dl_vlan_enable=True, vlan_vid=new_vid)
        vid_act = ofp.action.set_vlan_vid()
        vid_act.vlan_vid = new_vid
        
        #Insert flow with action -- set vid , Send packet matching the flow.Verify recieved packet is expected packet.
        wildcards = ofp.OFPFW_ALL ^ ofp.OFPFW_IN_PORT ^ ofp.OFPFW_DL_SRC ^ ofp.OFPFW_DL_DST ^ ofp.OFPFW_DL_TYPE ^ ofp.OFPFW_NW_SRC_ALL ^ ofp.OFPFW_NW_DST_ALL
        flow_match_test(self, config["port_map"], pkt=pkt, exp_pkt=exp_pkt,
                        wildcards=wildcards,
                        action_list=[vid_act])
        


