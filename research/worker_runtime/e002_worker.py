"""Network-none worker: only finite broker messages; no credential or host paths."""
import json
from pathlib import Path
import sys


def exchange(channel, **payload):
    print(json.dumps({'channel': channel, **payload}), flush=True)
    line = sys.stdin.readline(262145)
    if not line or len(line) > 262144:
        raise RuntimeError('broker disconnected or oversized response')
    value = json.loads(line)
    if 'error' in value:
        raise RuntimeError('broker refused action')
    return value['result']


def main():
    config = json.loads(Path('/workspace/PROMPT.txt').read_text())
    history = [{'role': 'user', 'content': config['prompt']}]
    # Every container starts a new history. No response or conversation IDs cross stages.
    while True:
        response = exchange('responses', history=history)
        output = response['output']
        history.extend(output)
        calls = [item for item in output if item.get('type') == 'function_call']
        if calls:
            for call in calls:
                result = exchange('tool', name=call['name'], arguments=json.loads(call['arguments']))
                history.append({'type': 'function_call_output', 'call_id': call['call_id'], 'output': json.dumps(result)})
            continue
        messages = [i for i in output if i.get('type') == 'message' and i.get('role') == 'assistant']
        if not messages:
            raise RuntimeError('no final assistant message')
        text = ''.join(p.get('text', '') for p in messages[-1].get('content', []) if p.get('type') == 'output_text')
        print(json.dumps({'channel': 'worker', 'line': text}), flush=True)
        return


if __name__ == '__main__':
    main()
