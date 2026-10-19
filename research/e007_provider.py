"""E007-only transport byte instrumentation; historical provider source stays unchanged."""
import http.client
import json
import socket
import ssl
import threading
import time
from .responses_provider import ResponsesProvider


class MeasuredProvider(ResponsesProvider):
    def respond(self,worker,*args,**kwargs):
        self.current_worker=worker
        try:
            return super().respond(worker,*args,**kwargs)
        finally:
            self.current_worker=None

    def request(self,method,endpoint,payload=None,timeout=30):
        if (method,endpoint) not in {('GET','/v1/models'),('POST','/v1/responses')}:
            raise PermissionError('unregistered endpoint')
        connection=http.client.HTTPSConnection(self.host,self.port,timeout=timeout,context=ssl.create_default_context())
        expired=threading.Event()
        deadline=time.monotonic()+timeout
        body=None if payload is None else json.dumps(payload,ensure_ascii=False).encode()
        measurement={'event':'transport_bytes','worker':getattr(self,'current_worker',None),'method':method,'endpoint':endpoint,
                     'request_body_bytes':len(body) if body else 0,'request_sent':False,'response_body_bytes':0,
                     'response_complete':False,'http_status':None,'scope':'actual HTTP body bytes only; no headers/TLS framing'}
        def expire():
            expired.set()
            if connection.sock is not None:
                try:
                    connection.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection.close()
        timer=threading.Timer(timeout,expire)
        timer.daemon=True
        timer.start()
        try:
            connection.connect()
            if expired.is_set():
                raise TimeoutError('provider total deadline expired')
            connection.sock.settimeout(max(.001,deadline-time.monotonic()))
            connection.request(method,endpoint,body=body,headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
            measurement['request_sent']=True
            response=connection.getresponse()
            measurement['http_status']=response.status
            raw=response.read(4*1024*1024+1)
            measurement['response_body_bytes']=len(raw)
            measurement['response_complete']=len(raw)<=4*1024*1024
            if expired.is_set() or time.monotonic()>=deadline:
                raise TimeoutError('provider total deadline expired')
            if len(raw)>4*1024*1024:
                raise ValueError('provider response exceeds byte envelope')
            if response.status!=200:
                raise RuntimeError('provider HTTP status '+str(response.status)+'; no retry or redirect')
            return json.loads(raw)
        finally:
            timer.cancel()
            connection.close()
            self.record(measurement)
