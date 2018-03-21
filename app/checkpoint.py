import ast
import base64
import os
import sqlite3
import time

from app import app
from app import sqlhelp

from cpapilib.Management import Management

class CheckPoint(Management):

    obj_map = {
        'host': 'hosts',
        'network': 'networks',
        'group': 'groups',
        'simple-gateway': 'gateways-and-servers',
        'access-role': 'access-roles',
        'service-tcp': 'services-tcp',
        'service-udp': 'services-udp',
        'service-group': 'service-groups'
    }

    def verify_db(self):
        """At login, ensure local object database exists.
        If not create it via sqlhelp, also create sqlite3 connection."""
        if self.domain:
            self.localdb = '{}{}_{}.db'.format(app.config['BASEDIR'],
                                               self.host, self.domain)
        else:
            self.localdb = '{}{}.db'.format(app.config['BASEDIR'],
                                            self.host)
        if not os.path.exists(self.localdb):
            app.logger.info('Creating local DB {}'.format(self.localdb))
            sqlhelp.createdb(self.localdb)
        app.logger.info('Connecting to local database {}'.format(self.localdb))
        self.dbobj = sqlhelp.sqlhelper(self.localdb)

    def pre_data(self):
        """Data to establish after login to make less calls later to the API."""
        # Black omitted as defalut option.
        self.all_colors = [
            'aquamarine', 'blue', 'crete blue', 'burlywood', 'cyan',
            'dark green', 'khaki', 'orchid', 'dark orange', 'dark sea green',
            'pink', 'turquoise', 'dark blue', 'firebrick', 'brown',
            'forest green', 'gold', 'dark gold', 'gray', 'dark gray',
            'light green', 'lemon chiffon', 'coral', 'sea green', 'sky blue',
            'magenta', 'purple', 'slate blue', 'violet red', 'navy blue',
            'olive', 'orange', 'red', 'sienna', 'yellow'
        ]
        app.logger.info('Retrieving pre-load data.')
        self.getallcommands()
        self.getalltargets()
        self.getalllayers()

    def object_status(self):
        self.local_obj = self.dbobj.total_objects()
        self.remote_obj = self.count_remote_objects()
        app.logger.debug('Object count - Local: {} // Remote: {}'.format(self.local_obj, self.remote_obj))
        return {'local': self.local_obj, 'remote': self.remote_obj}

    def count_remote_objects(self):
        """Count objects for local comparison"""
        # Reset count for consecutive pulls.
        remote_obj = 0
        for plural in self.obj_map.values():
            payload = {'limit': 1}
            response = self._api_call('show-{}'.format(plural), **payload)
            if 'total' in response:
                remote_obj += response['total']
        return remote_obj

    def get_remote_uids(self):
        all_remote_uids = []
        for plural in self.obj_map.values():
            self.offset = 0
            payload = {'limit': self.max_limit, 'offset': self.offset, 'details-level': 'uid'}
            response = self._api_call('show-{}'.format(plural), **payload)
            for cpobject in response['objects']:
                all_remote_uids.append(cpobject)
            if 'to' in response and response['total'] != 0:
                while response['to'] != response['total']:
                    self.offset += self.max_limit
                    payload = {'limit': self.max_limit, 'offset': self.offset, 'details-level': 'uid'}
                    response = self._api_call('show-{}'.format(plural), **payload)
                    for cpobject in response['objects']:
                        all_remote_uids.append(cpobject)
        return all_remote_uids

    def full_sync(self):
        """Collect objects for localdb."""
        for plural in self.obj_map.values():
            self.offset = 0
            payload = {'limit': self.max_limit, 'offset': self.offset}
            app.logger.info(
                'Retrieving {} from remote database. Offset:{}, Limit:{}'.
                format(plural, self.offset, self.max_limit))
            response = self._api_call('show-{}'.format(plural), **payload)
            for cpobject in response['objects']:
                self.dbobj.insert_object(cpobject)
            self.dbobj.dbconn.commit()
            if 'to' in response and response['total'] != 0:
                while response['to'] != response['total']:
                    self.offset += self.max_limit
                    payload = {'limit': self.max_limit, 'offset': self.offset}
                    app.logger.info(
                        'Retrieving {} from remote database. Offset:{}, Limit:{}'.
                        format(plural, self.offset, self.max_limit))
                    response = self._api_call('show-{}'.format(plural), **payload)
                    for cpobject in response['objects']:
                        self.dbobj.insert_object(cpobject)
                    self.dbobj.dbconn.commit()

    def delta_sync(self):
        """Resolve descrepency in local database."""
        remote_uids = self.get_remote_uids()
        local_uids = self.dbobj.get_local_uids()
        delete_list = [uid for uid in local_uids if uid not in remote_uids]
        sync_list = [uid for uid in remote_uids if uid not in local_uids]
        for uid in delete_list:
            app.logger.info('Deleting local object {}'.format(uid))
            self.dbobj.delete_object(uid)
        for uid in sync_list:
            app.logger.info('Syncing remote object {}'.format(uid))
            self.sync_single(uid)
        self.dbobj.dbconn.commit()

    def delete_single(self, uid, retry=0):
        if retry < 10:
            try:
                self.dbobj.delete_object(uid)
            except sqlite3.OperationalError:
                app.logger.warn('Database locked while performing delete operation.')
                time.sleep(0.1)
                self.delete_single(uid, retry + 1)
        else:
            app.logger.error('Max retries exceeded while attempting delete operation.')

    def insert_single(self, cpobject, retry=0):
        if retry < 10:
            try:
                self.dbobj.insert_object(cpobject)
            except sqlite3.OperationalError:
                app.logger.warn('Database locked while performing insert operation.')
                time.sleep(0.1)
                self.insert_single(cpobject, retry + 1)
        else:
            app.logger.error('Max retries exceeded while attempting insert operation.')

    def sync_single(self, uid):
        fpayload = {'uid': uid}
        fresponse = self._api_call('show-object', **fpayload)
        spayload = {'uid': uid}
        sresponse = self.show(fresponse['object']['type'], **spayload)
        self.insert_single(sresponse)

    def getallcommands(self):
        """Get all available commands for custom command page."""
        getcommands_result = self.shows('command')
        self.all_commands = [obj['name'] for obj in getcommands_result['commands']]

    def getalltargets(self):
        """Get all gateways and servers from Check Point."""
        self.all_targets = []
        self.offset = 0
        payload = {'limit': self.small_limit, 'offset': self.offset}
        response = self.shows('gateways-and-server', **payload)
        for target in response['objects']:
            self.all_targets.append(target['name'])
        while response['to'] != response['total']:
            self.offset += self.small_limit
            payload = {'limit': self.small_limit, 'offset': self.offset}
            response = self.shows('gateways-and-server', **payload)
            for target in response['objects']:
                self.all_targets.append(target['name'])

    def getalllayers(self):
        """Retrieve all rule base layers from management server."""
        self.all_layers = []
        self.offset = 0
        payload = {'limit': self.small_limit, 'offset': self.offset}
        response = self.shows('access-layer', **payload)
        for layer in response['access-layers']:
            self.all_layers.append((layer['name'], layer['uid']))
        # In case there is ever a way to have 0 layers
        if 'to' in response and response['total'] != 0:
            while response['to'] != response['total']:
                self.offset += self.small_limit
                payload = {'limit': self.small_limit, 'offset': self.offset}
                response = self.shows('access-layer', **payload)
                for layer in response['access-layers']:
                    self.all_layers.append((layer['name'], layer['uid']))

    def customcommand(self, command, payload):
        """Validate payload and send command to server."""
        try:
            payload = ast.literal_eval(payload)
        except ValueError:
            return 'Invalid input provided.'
        return self._api_call(command, **payload)

    def runcommand(self, targets, script):
        """Issue command against Check Point targets, verify task is complete
        on each gateways and return response for each target."""
        taskreturn = []
        payload = {
            'script-name': 'cpapi',
            'script': script,
            'targets': targets
        }
        response = self.command('run', 'script', **payload)
        if 'tasks' in response:
            for task in response['tasks']:
                target = task['target']
                taskid = task['task-id']
                taskresponse = self.monitortask(target, taskid)
                taskreturn.append(taskresponse)
        return taskreturn

    def monitortask(self, target, taskid):
        """Run gettask until task is complete and we can return response."""
        complete = False
        retry = 0
        while not complete and retry < 30:
            response = self.gettask(taskid)
            if response['tasks'][0]['progress-percentage'] == 100:
                complete = True
                if response['tasks'][0]['task-details'][0]['responseMessage']:
                    base64resp = response['tasks'][0]['task-details'][0]['responseMessage']
                    asciiresp = self.base64_ascii(base64resp)
                    return {
                        'target': target,
                        'status': response['tasks'][0]['status'],
                        'response': asciiresp
                    }
                else:
                    return {
                        'target': target,
                        'status': response['tasks'][0]['status'],
                        'response': 'Not Available'
                    }
            retry += 1
            time.sleep(1)
        app.logger.warn('Script did not finish within time limit on {}.'.format(target))
        return {
            'target': target,
            'status': 'Task did not complete within 30 seconds.',
            'response': 'Unavailable.'
        }

    def gettask(self, task):
        """Get individual task information."""
        payload = {'task-id': task, 'details-level': 'full'}
        return self.show('task', **payload)

    @staticmethod
    def base64_ascii(base64resp):
        """Converts base64 to ascii for run command/showtask."""
        return base64.b64decode(base64resp).decode('utf-8')

    def show_rules(self, **kwargs):
        """Recieves Layer UID, limit, offset."""
        all_rules = {'rulebase': []}
        app.logger.info('Retrieving rules for - {}'.format(kwargs))
        response = self.show('access-rulebase', **kwargs)
        all_rules.update({'to': response['to'], 'total': response['total']})
        self._filter_rules(all_rules, response)
        return all_rules

    def _filter_rules(self, all_rules, response):
        """Recieves show_rules response and performs logic against whether
        rules are sections or rules."""
        for rule in response['rulebase']:
            if 'type' in rule:
                if rule['type'] == 'access-rule':
                    final = self._filter_rule(rule, response['objects-dictionary'])
                    all_rules['rulebase'].append(final)
                elif rule['type'] == 'access-section':
                    if 'name' in rule:
                        section = rule['name']
                    else:
                        section = ''
                    all_rules['rulebase'].append({'type': 'accesssection', 'name': section})
            if 'rulebase' in rule:
                for subrule in rule['rulebase']:
                    final = self._filter_rule(subrule, response['objects-dictionary'])
                    all_rules['rulebase'].append(final)
        return all_rules

    @staticmethod
    def _filter_rule(rule, object_dictionary):
        """Recieves rule and replaces UID with Name."""
        filteredrule = {}
        if 'name' in rule:
            name = rule['name']
        else:
            name = ''
        num = rule['rule-number']
        src = rule['source']
        src_all = []
        dst = rule['destination']
        dst_all = []
        srv = rule['service']
        srv_all = []
        act = rule['action']
        if rule['track']['type']:
            trc = rule['track']['type']
        else:
            trc = rule['track']
        trg = rule['install-on']
        trg_all = []
        for obj in object_dictionary:
            if name == obj['uid']:
                name = obj['name']
            if num == obj['uid']:
                num = obj['name']
            if act == obj['uid']:
                act = obj['name']
            if trc == obj['uid']:
                trc = obj['name']
        for srcobj in src:
            for obj in object_dictionary:
                if srcobj == obj['uid']:
                    src_all.append((obj['name'], srcobj))
        for dstobj in dst:
            for obj in object_dictionary:
                if dstobj == obj['uid']:
                    dst_all.append((obj['name'], dstobj))
        for srvobj in srv:
            for obj in object_dictionary:
                if srvobj == obj['uid']:
                    srv_all.append((obj['name'], srvobj))
        for trgobj in trg:
            for obj in object_dictionary:
                if trgobj == obj['uid']:
                    trg_all.append((obj['name'], trgobj))
        filteredrule.update({
            'type': 'accessrule',
            'number': num,
            'name': name,
            'source': src_all,
            'source-negate': rule['source-negate'],
            'destination': dst_all,
            'destination-negate': rule['destination-negate'],
            'service': srv_all,
            'service-negate': rule['service-negate'],
            'action': act,
            'track': trc,
            'target': trg_all,
            'enabled': rule['enabled']
        })
        return filteredrule

    def show_object(self, objuid):
        payload = {'uid': objuid}
        response = self.show('object', **payload)
        payload = {'uid': objuid, 'details-level': 'full'}
        responsetwo = self.show('{}'.format(response['object']['type']), **payload)
        return responsetwo
