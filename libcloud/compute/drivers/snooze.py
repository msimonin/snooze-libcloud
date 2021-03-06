from libcloud.compute.base import NodeDriver, Node, NodeSize
from libcloud.compute.base import NodeState, NodeImage
from libcloud.compute.types import Provider
from libcloud.common.types import MalformedResponseError


from libcloud.common.base import Connection
from libcloud.common.base import Response

from xml.dom.minidom import parseString
import json
import httplib
import time

HTTP_RETRIES = 2
POLLING_INTERVAL = 2
POLLING_RETRIES = 20

class SnoozeResponse(Response):
    """
    Snooze http response class
    """
    node_driver = None
    def success(self):
        i = int(self.status)
        return i >= 200 and i <=299

    def has_content_type(self, content_type):
        content_type_value = self.headers.get('content-type') or ''
        content_type_value = content_type_value.lower()
        return content_type_value.find(content_type.lower()) > -1

    def parse_body(self):
        if self.status == httplib.NO_CONTENT or not self.body:
            return None
        if self.has_content_type('application/json'):
          try:
              return json.loads(self.body)
          except:
              # hum hum ... sometimes rest answer has application/json but are not json (eg String)
              return self.body
              """
              raise MalformedResponseError(
                  'Failed to parse JSON',
                  body=self.body,
                  driver=self.node_driver)
              """
        else:
            return self.body

class SnoozeConnection(Connection):
    """
    Snooze Connection class
    """
    responseCls = SnoozeResponse
    def __init__(self,host,port
    ):
        super(SnoozeConnection, self).__init__(False, host, port)
        

           
           
class SnoozeNodeDriver(NodeDriver):
    """
    Snooze (http://snooze.inria.fr) node driver.

    """
    connectionCls = SnoozeConnection
    type = Provider.SNOOZE
    name = 'Snooze'
    website = 'http://snooze.inria.fr'
    

    
    def __init__(self,host,port):
        """
        
        """
        self.connection_bs = SnoozeConnection(host,port)
        self.connection_bs.driver = self 
        
        self.connection_gl = SnoozeConnection(host,port)
        self.connection_gl.driver = self 
        
        self.connection_gm = SnoozeConnection(host,port)
        self.connection_gl.driver = self
        
    def get_and_set_groupleader(self):
      data_str = self.get_groupleader()
      data = json.loads(data_str)

      host = data["listenSettings"]["controlDataAddress"]["address"]
      port = data["listenSettings"]["controlDataAddress"]["port"]
      self.connection_gl = SnoozeConnection(host,port)
      self.connection_gl.driver = self 
      return data["listenSettings"]["controlDataAddress"] 

    def get_groupleader(self):
        """
        Gets the group leader addresses
        """
        attempt = 0
        while attempt < HTTP_RETRIES:
            attempt += 1
            try:
                resp = self.connection_bs.request("/bootstrap?getGroupLeaderDescription",method='GET')
                break
            except  httplib.HTTPException:
                continue
        """ 
        #json_data = resp.body
        #data = json.loads(json_data)
        """
        return  resp.body

    def get_and_set_assigned_groupmanager(self,node):
        """
        Gets the assigned group manager 
        """
        metadata = node.extra ;
        group_manager_address = metadata.get("groupManagerControlDataAddress")
        host = group_manager_address.get("address")
        port = group_manager_address.get("port")
        self.connection_gm = SnoozeConnection(host,port)
        self.connection_gm.driver = self
        
    def get_gl_repository(self,num=5):
        """
        Gets the gl repository 
        """
        self.get_and_set_groupleader()
        content=str(num)
        headers = {"Content-type": "application/json"}
        resp = self.connection_gl.request('/groupmanager?getGroupLeaderRepositoryInformation', headers=headers,method='POST',data=content)
        server_object = resp.object
        return server_object
        
    def polling_for_response(self,task_id):
        server_object = None 
        i = 1  
        time.sleep(POLLING_INTERVAL)
        server_object="{}"
        while i <= POLLING_RETRIES :
            resp = self.connection_gl.request("groupmanager?getVirtualClusterResponse",method='POST',data=task_id)
            if not resp.object:
                i=i+1
                time.sleep(POLLING_INTERVAL)
            else :
                server_object = resp.object
                break 
        return server_object

    
        
    def get_info(self,node):
        """
        Get info for a node.
        """      
        metadata = node.extra ;
        self.get_and_set_assigned_groupmanager(node)
        
        metadata_request = {"virtualMachineLocation": metadata.get("virtualMachineLocation"),
                            "numberOfMonitoringEntries" : 10
                            }
        resp = self.connection_gm.request('/groupmanager?getVirtualMachineMetaData',method='POST',data=json.dumps(metadata_request))
        return json.loads(resp.object)


    def _to_node(self,api_node):
        meta_data = api_node.get("virtualMachineMetaData",None)
        if meta_data is None:
            return None
        else:
	    return [self.__to_node(node) for node in meta_data]	
        
    def __to_node(self,meta_data):
        return Node(
                id=meta_data.get("virtualMachineLocation").get("virtualMachineId",None),
                name=meta_data.get("virtualMachineLocation").get("virtualMachineId",None),
                state=meta_data.get("status","UNKNOWN"),
                public_ips=meta_data.get("ipAddress","UNKNOWN"),
                private_ips=None,
                driver=self,
                extra = meta_data
            )
        
    def list_nodes(self):
        """
        Return the list of nodes in Snooze system
        """
        nodes = []
        resp=self.get_gl_repository()
        group_managers = resp.get("groupManagerDescriptions")
        for group_manager in group_managers:
            control_setting=group_manager.get("listenSettings").get("controlDataAddress") 
            host = control_setting.get("address")
            port = control_setting.get("port")
            connection_gm = SnoozeConnection(host,port)
            connection_gm.driver = self
            gm_repository = self.get_gm_repository(connection_gm)
            local_controllers = gm_repository.get("localControllerDescriptions")
            for local_controller in local_controllers:
                metadatas = local_controller.get("virtualMachineMetaData")
                for virtual_machine, metadata in metadatas.iteritems():
                    nodes.append(self.__to_node(metadata)) 
                    
        return nodes
        
        
    def get_gm_repository(self,connection_gm):
        content=str(5)
        headers = {"Content-type": "application/json"}
        resp = connection_gm.request('/groupmanager?getGroupManagerRepositoryInformation', headers=headers,method='POST',data=content)
        server_object = resp.object
        return server_object
          
    def get_name_from_template(self,template):
        dom = parseString(template)
        xmlTag = dom.getElementsByTagName('name')[0].toxml()
        xmlData=xmlTag.replace('<name>','').replace('</name>','')
        return xmlData
     
    def shutdown(self,node):
        """
        shutdown a node
        @param       node: node 
        @type        node: L{Node}
        """
        metadata = node.extra 
        self.get_and_set_assigned_groupmanager(node)
        location = node.extra.get("virtualMachineLocation")
        resp = self.connection_gm.request("groupmanager?shutdownVirtualMachine",method='POST',data=json.dumps(location))
        
    def suspend(self,node):
        """
        suspend a node
        @param       node: node 
        @type        node: L{Node}
        """
        metadata = node.extra 
        self.get_and_set_assigned_groupmanager(node)
        location = node.extra.get("virtualMachineLocation")
        resp = self.connection_gm.request("groupmanager?suspendVirtualMachine",method='POST',data=json.dumps(location))

    def resume(self,node):
        """
        resume a node
        @param       node: node 
        @type        node: L{Node}
        """
        metadata = node.extra
        self.get_and_set_assigned_groupmanager(node)
        location = node.extra.get("virtualMachineLocation")
        resp = self.connection_gm.request("groupmanager?resumeVirtualMachine",method='POST',data=json.dumps(location))
    
    def destroy(self,node):
        """
        destroy a node
        @param       node: node 
        @type        node: L{Node}
        """
        metadata = node.extra
        self.get_and_set_assigned_groupmanager(node)
        location = node.extra.get("virtualMachineLocation")
        resp = self.connection_gm.request("groupmanager?destroyVirtualMachine",method='POST',data=json.dumps(location))
    
    def migrate(self,node,newLocation):
        """
        migrate a node to a new location
        @param       node: node 
        @type        node: L{Node}

        @param       newLocation : new location
        @type        newLocation: C{dict}
        """
        metadata = node.extra
        self.get_and_set_assigned_groupmanager(node)
        location = node.extra.get("virtualMachineLocation")
        migration_request = {
                                "sourceVirtualMachineLocation" : location,
                                "destinationVirtualMachineLocation" : newLocation,
                                "destinationHypervisorSettings" : None,
                                "migrated" : False
                             }
        self.get_and_set_groupleader()
        resp = self.connection_gl.request('/groupmanager?migrateVirtualMachine',method='POST',data=json.dumps(migration_request))
        
class SnoozeNodeDriverV0(SnoozeNodeDriver):
    """ 
    Version 0 : working with snooze 1.0.0
    """
    def create_node(self,libvirt_templates=None, raw_templates=None,
                         tx=12800,
                         rx=12800,
                         **kwargs):
        """
        StartVirtualCluster
        @param       libvirt_template:  template path
        @type        libvirt_template: C{str}

        @param       raw_template:  raw template
        @type        raw_template: C{str}

        @param       tx: network transmission capacity
        @type        tx: C{int}
        
        @param       rx: network receive capacity
        @type        rx: C{int}
        """
        uri = self.get_and_set_groupleader()
        
        templates = []
        if (libvirt_templates):
            for t in libvirt_templates:
            	f = open(t)
            	templates.append( f.read().replace('\n','').replace('\r',''))
        else:
            templates = kwargs.get("raw_templates",None)
        
        #name = self.get_name_from_template(template)
        attributes = dict()
        attributes["virtualMachineTemplates"] = list()
        for template in templates:
          attribute = {
            "libVirtTemplate":template,
            "networkCapacityDemand" : 
            {
              "txBytes" : tx,
              "rxBytes" : rx,
            }
          } 
          attributes["virtualMachineTemplates"].append(attribute)	
        
        resp = self.connection_gl.request("groupmanager?startVirtualCluster",method='POST',data=json.dumps(attributes))
        task_id = resp.object
        
        server_object = self.polling_for_response(task_id)
        return self._to_node(server_object)


class SnoozeNodeDriverV1(SnoozeNodeDriver):
    """
    Version 1 : work with snooze v 2.0
    """
    def create_node(self, **kwargs):
        """
        create a new node
        We have to choose between create_node_raw and create_node_id_based
        """
        #try:
        image = kwargs.get("image",None)
        if image is None:
            return self.create_node_raw(**kwargs)
        else:
            return self.create_node_id_based(**kwargs)
            
        
    def create_node_raw(self, libvirt_template=None, tx=12800, rx=12800, **kwargs):
        """
        startVirtualCluster
        @param       libvirt_template:  libvirt_template
        @type        libvirt_template: C{str}

        @param       tx: network transmission capacity
        @type        tx: C{int}
        
        @param       rx: network receive capacity
        @type        rx: C{int}
        """
        uri = self.get_and_set_groupleader()
        
        libvirt_template = kwargs.get("libvirt_template")
        tx = kwargs.get("tx")
        rx = kwargs.get("rx")
         
        f = open(libvirt_template)
        template = f.read().replace('\n','').replace('\r','') 
        name = self.get_name_from_template(template)
    
        attributes = {"virtualMachineTemplates":
                         [
                             {
                                "type": "raw",
                                "libVirtTemplate":template,
                                "networkCapacityDemand" : 
                                   {
                                    "txBytes" : tx,
                                    "rxBytes" : rx,
                                    }
                             }
                          ]
                      }
        resp = self.connection_gl.request("groupmanager?startVirtualCluster",method='POST',data=json.dumps(attributes))
        task_id = resp.object

        server_object = self.polling_for_response(task_id)
        return self._to_node(server_object)
        
    
    def create_node_id_based(self, **kwargs):
        """
        Create a node.
        """      
        uri = self.get_and_set_groupleader()
        name = kwargs['name']
        image = kwargs['image']
        size = kwargs['size']

        attributes = {"virtualMachineTemplates":
                         [
                             {
                                "type": "id_based",
                                "name": name,
                                "imageIdentifier": str(image.id),
                                "vcpuDemand": "1",
                                "memoryDemand": str(size.ram*1000),
                                "networkCapacityDemand" : 
                                   {
                                    "txBytes" : str(2*size.bandwidth),
                                    "rxBytes" : str(size.bandwidth),
                                    }
                             }
                          ]
                      }
        
        resp = self.connection_gl.request("groupmanager?startVirtualCluster",method='POST',data=json.dumps(attributes))
        task_id = resp.object
        
        
        server_object = self.polling_for_response(task_id)
        return self._to_node(server_object)
        
    def list_sizes(self):
        """
           From Dummy Driver
        """

        return [
            NodeSize(id=1,
                     name="Small",
                     ram=128,
                     disk=4,
                     bandwidth=500,
                     price=4,
                     driver=self),
            NodeSize(id=2,
                     name="Medium",
                     ram=512,
                     disk=16,
                     bandwidth=1500,
                     price=8,
                     driver=self),
            NodeSize(id=3,
                     name="Big",
                     ram=4096,
                     disk=32,
                     bandwidth=2500,
                     price=32,
                     driver=self),
            NodeSize(id=4,
                     name="XXL Big",
                     ram=4096 * 2,
                     disk=32 * 4,
                     bandwidth=2500 * 3,
                     price=32 * 2,
                     driver=self),
        ]    
        
    
    def list_images(self):
        resp = self.connection_bs.request('/images?getList')
        json_data = resp.body
        data = json.loads(json_data)
        return self._to_images(data)    
            
        
    
    
    def _to_images(self, object):
        images = []
        for image in object["images"]:
            images.append(self._to_image(image))

        return images

    def _to_image(self, element):
        return NodeImage(id=element.get('id'),
                         name=element.get('name'),
                         driver=self,
                         extra={}
                         )
        
   
       
