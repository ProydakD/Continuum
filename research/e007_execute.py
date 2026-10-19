"""One fresh network-none container, real narrow MCP bridge, no worker retries."""
import json
import queue
import subprocess
import threading
import time
from .common import PROJECT, command, source_hashes, write_json
from .e007_archive import SessionBridge
from .e007_protocol import TOOLS, prompt
from .profiles import create_worker
from .sandbox import container_command
from .supervisor import read_lines


def execute(study, reg, job, world, provider):
    run = study/'units'/job['id']
    stage = job['stage']
    worker = run/'workers'/stage
    if worker.exists():
        raise RuntimeError('worker directory already exists; never relaunch a context')
    create_worker(worker, stage, 'none')
    write_json(worker/'repo/PROMPT.txt', {'prompt': prompt(job, world)})
    before = source_hashes(worker)
    write_json(run/'context-manifest.json', before)
    name = f'continuum-{study.name}-{job["id"]}'
    argv = container_command(reg['image'], name, worker, ['/runtime/e002_worker.py'])
    role = job['role']
    limit = reg['limits'][role+'_seconds']
    start = time.monotonic()
    report = {'status': 'failed', 'exit_status': None, 'job': job, 'fixture': reg['fixture']}
    process = bridge = timer = None
    with (run/'supervisor/session.jsonl').open('x', encoding='utf-8') as log, (run/'supervisor/session.stderr.txt').open('x', encoding='utf-8') as err:
        try:
            bridge = SessionBridge(run, stage, [], log, 'scripted-fixture' if reg['fixture'] else provider.model)
            bridge.configure(job)
            bridge.emit({'event':'command_execution','command':argv,'at':time.time()})
            process = subprocess.Popen(argv, cwd=PROJECT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True, encoding='utf-8')
            timer = threading.Timer(limit, lambda: command(['docker','rm','-f',name], timeout=15))
            timer.daemon = True
            timer.start()
            inbox = queue.Queue(maxsize=128)
            threading.Thread(target=read_lines, args=(process.stdout,inbox,'worker'), daemon=True).start()
            final, requests, crashed = None, 0, False
            while True:
                remaining = limit-(time.monotonic()-start)
                if remaining<=0 or (study/'STOP').exists():
                    raise TimeoutError('worker deadline or STOP')
                _, line = inbox.get(timeout=remaining)
                if line is None:
                    break
                if len(line)>262144:
                    raise ValueError('oversized worker message')
                event = json.loads(line)
                bridge.emit({'event':'worker_message','message':event})
                if event['channel']=='responses':
                    requests += 1
                    if requests>reg['limits']['responses_per_context']:
                        raise ValueError('registered response count ceiling')
                    try:
                        response = provider.respond(job['id'],event['history'],TOOLS[role], timeout=min(remaining,reg['limits']['request_seconds']),
                                                    max_output_tokens=reg['limits']['development_output_tokens' if role in ('designer','critic') else 'application_output_tokens'])
                    except Exception:
                        report['failure_origin']='provider'
                        raise
                elif event['channel']=='tool':
                    response = bridge.call(event['name'],event['arguments'])
                    bridge.emit({'event':'tool_result','name':event['name'],'arguments':event['arguments'],'value':response})
                    if role=='writer' and job.get('control')=='crash' and bridge.saved:
                        killed = command(['docker','kill',name], timeout=15)
                        bridge.emit({'event':'injected_crash_after_commit','kill_result':killed,'at':time.time(),'receipt_delivered':False})
                        crashed = True
                        break
                elif event['channel']=='worker':
                    if final is not None:
                        raise ValueError('multiple finals')
                    final=json.loads(event['line'])
                    continue
                else:
                    raise PermissionError('unregistered channel')
                process.stdin.write(json.dumps({'result':response})+'\n')
                process.stdin.flush()
            report['exit_status']=process.wait(timeout=15)
            if crashed:
                if process.returncode!=137 or not bridge.saved:
                    raise ValueError('crash injection not observed as committed exit 137')
                report['status']='injected_crash_after_commit'
            else:
                if process.returncode!=0 or final is None:
                    raise ValueError('no successful final output')
                bridge.finish(final)
                report.update(status='budget_rejected' if role=='writer' and not bridge.saved else 'completed', answer=final)
        except Exception as exc:
            report.update(failure_type=type(exc).__name__,failure=str(exc))
        finally:
            if timer:
                timer.cancel()
            if process:
                if process.poll() is None:
                    command(['docker','rm','-f',name], timeout=15)
                    process.wait(timeout=15)
                report['exit_status']=process.returncode
                process.stdin.close()
                process.stdout.close()
            if bridge:
                report.update(saved=bridge.saved,save_attempts=bridge.attempts)
                bridge.close()
    if source_hashes(worker)!=before:
        report.update(status='failed',failure_origin='safeguard',failure_type='PermissionError',failure='worker inputs changed')
    report['seconds']=time.monotonic()-start
    write_json(run/'result.json',report)
    return report
