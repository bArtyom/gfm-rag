"""Reference identity and cleanup of only a session created by this experiment."""
import hashlib
import json
import os
from pathlib import Path
import signal
import time


def read_reference_rows(cfg):
    raw=(Path(cfg['dataset_root'])/'dev.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=cfg['questions_sha256']:
        raise ValueError('Reference dataset differs from frozen input')
    return json.loads(raw)


def session_members(session_id):
    result={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            fields=(path/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[3])==session_id and fields[0]!='Z':
                result[int(path.name)]={'start_ticks':int(fields[19]),'session_id':session_id}
        except (OSError,ValueError,IndexError):continue
    return result


def stop_owned_session(process,timeout=15.):
    sid=process.pid
    before=session_members(sid)
    def send(sig):
        snapshot=session_members(sid)
        for pid,identity in snapshot.items():
            # Verify start time immediately before each signal, guarding PID reuse.
            current=session_members(sid).get(pid)
            if current==identity:
                try:os.kill(pid,sig)
                except ProcessLookupError:pass
    send(signal.SIGTERM)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        process.poll()
        if not session_members(sid):break
        time.sleep(.1)
    if session_members(sid):send(signal.SIGKILL)
    try:process.wait(timeout=5)
    except Exception:pass
    deadline=time.monotonic()+5
    while session_members(sid) and time.monotonic()<deadline:time.sleep(.1)
    remaining=session_members(sid)
    if remaining:raise RuntimeError('Owned service descendants still alive')
    return {'owned_session_id':sid,'initial_owned_members':before,'remaining_owned_members':remaining,
        'all_owned_processes_exited':True}
