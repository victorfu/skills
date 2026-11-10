"""Durable, acknowledged hybrid watcher. Webhooks only invalidate API snapshots."""
import hashlib
import json
from pathlib import Path
import time
import uuid

import watch_pr as api


def versions(items):
    # Hash only what a reviewer can change: the text and, for reviews, the verdict.
    # Diff coordinates such as `line` move or become null when the PR is pushed to.
    return {item['key']: hashlib.sha256(
                json.dumps([item.get('body'), item.get('state')]).encode()).hexdigest()
            for item in items}


def snapshot(host, repo, number, ignored):
    # Keep full bodies for versioning; emitted excerpts remain bounded.
    for _ in range(3):
        pr = api.fetch_pr(host, repo, number)
        items = api.fetch_feedback(host, repo, number, ignored, full=True)
        checks = api.fetch_checks(host, repo, number)
        latest = api.fetch_pr(host, repo, number)
        if pr['headRefOid'] == latest['headRefOid'] and pr['state'] == latest['state']:
            return latest, items, checks
    raise api.GhError('PR head changed repeatedly during refresh; retry')


def read_signal(path):
    # Windows can refuse a read while the receiver is replacing the file.
    for attempt in range(3):
        try:
            return api.load_state(path)
        except OSError:
            if attempt == 2:
                raise
            time.sleep(0.05)


def signal_problem(path, target, now):
    """Return (signal, problem); problem is None only for a healthy receiver."""
    try:
        signal = read_signal(path)
    except (OSError, ValueError) as error:
        return None, f'signal file unreadable: {error}'
    if signal is None:
        return None, 'no signal file; receiver not started'
    if not isinstance(signal, dict):
        return None, 'signal file is not a receiver signal'
    if signal.get('target') != target:
        return signal, 'receiver is watching a different PR'
    if not signal.get('active'):
        return signal, signal.get('reason') or 'receiver is not active'
    heartbeat = signal.get('heartbeat')
    if not isinstance(heartbeat, (int, float)) or not 0 <= now - heartbeat <= 15:
        return signal, 'receiver heartbeat is stale'
    return signal, None


def signal_status(path, target, now):
    signal, problem = signal_problem(path, target, now)
    return (None, False) if problem else (signal.get('generation'), True)


def acknowledge(state, batch_id, now):
    pending = state.get('pending')
    if not pending or pending['event']['batch_id'] != batch_id:
        if state.get('last_ack') == batch_id:
            return  # Safe retry after a lost command response.
        raise ValueError('Acknowledgement does not match pending batch')
    state['seen_versions'].update(pending.get('versions', {}))
    if pending.get('ci_head') and pending['ci_head'] not in state['ci_reported']:
        state['ci_reported'].append(pending['ci_head'])
    state['pending'] = None
    state['settling'] = {}
    state['quiet_since'] = now
    state['last_ack'] = batch_id


def stage(state, event, item_versions=None, ci_head=None):
    event['batch_id'] = uuid.uuid4().hex
    state['pending'] = {'event': event, 'versions': item_versions or {}, 'ci_head': ci_head}
    return event


def evaluate(state, pr, items, checks, now, quiet, settle):
    base = {'url': pr['url'], 'head': pr['headRefOid']}
    if pr['state'] != 'OPEN':
        return dict(base, event='closed', pr_state=pr['state'])
    if pr['headRefOid'] != state['head']:
        state['head'] = pr['headRefOid']
        state['quiet_since'] = now
    pending = state.get('pending')
    if pending:
        if pending.get('ci_head') and pending['ci_head'] != state['head']:
            state['pending'] = None  # Old-head CI cannot authorize a new-head fix.
        else:
            return pending['event']
    current = versions(items)
    fresh = {key: value for key, value in current.items()
             if state['seen_versions'].get(key) != value}
    if fresh != state.get('settling', {}):
        state['settling'] = fresh
        state['last_new_at'] = now
        if fresh:
            state['quiet_since'] = now
    status, failing, _ = api.summarize_checks(checks)
    if fresh and now - state['last_new_at'] >= settle:
        excerpts = [{**item, 'body': api.excerpt(item.get('body'))}
                    for item in items if item['key'] in fresh]
        return stage(state, dict(base, event='feedback', items=excerpts), fresh)
    if not fresh and status == 'failing' and state['head'] not in state['ci_reported']:
        return stage(state, dict(base, event='ci_failed', failing_checks=failing), ci_head=state['head'])
    if not fresh and status != 'pending' and now - state['quiet_since'] >= quiet:
        return dict(base, event='quiet', ci=status, failing_checks=failing,
                    quiet_seconds=int(now - state['quiet_since']))
    return None


def run(args):
    for name in ('interval', 'quiet', 'settle', 'max_wait'):
        if getattr(args, name) < (1 if name == 'interval' else 0):
            raise ValueError(f'Invalid {name}')
    host, repo, number = api.parse_target(args)
    target = {'host': host, 'repo': repo, 'pr': number}
    path, signal = Path(args.state), Path(args.signal)
    if path.resolve() == signal.resolve():
        raise ValueError('State and signal must use separate files')
    state = api.load_state(path)
    if state and state.get('target') != target:
        raise ValueError('State belongs to another PR; choose a different file')
    if state and state.get('mode') != 'hybrid':
        raise ValueError('Use a separate state file for hybrid mode')
    if args.ack:
        if not state:
            raise ValueError('Cannot acknowledge missing state')
        acknowledge(state, args.ack, time.time())
        api.save_state(path, state)
    ignored = {name.lower() for name in args.ignore_author}
    if not args.include_self:
        ignored.add(api.gh('api', '--hostname', host, 'user', '--jq', '.login').strip().lower())
    started = time.monotonic()
    while True:
        # Sample generation BEFORE fetching: a notification during fetch triggers another refresh.
        generation, active = signal_status(signal, target, time.time())
        pr, items, checks = snapshot(host, repo, number, ignored)
        now = time.time()
        status, failing, buckets = api.summarize_checks(checks)
        if state is None:
            state = {'mode': 'hybrid', 'version': 1, 'target': target,
                     'head': pr['headRefOid'], 'seen_versions': {}, 'ci_reported': [],
                     'quiet_since': now, 'settling': {}}
            if pr['state'] != 'OPEN':
                event = dict(event='closed', url=pr['url'], head=pr['headRefOid'], pr_state=pr['state'])
            else:
                event = stage(state, dict(event='baseline', url=pr['url'], head=pr['headRefOid'],
                              pr_state=pr['state'], existing_feedback=len(items), ci=status,
                              failing_checks=failing, ignored_authors=sorted(ignored)),
                              versions(items), pr['headRefOid'] if status == 'failing' else None)
        else:
            event = evaluate(state, pr, items, checks, now, args.quiet, args.settle)
        api.save_state(path, state)
        if event:
            api.emit(**event)
            return
        elapsed = time.monotonic() - started
        if elapsed >= args.max_wait:
            fields = {'receiver_active': active}
            if not active:
                # Say why the watch is polling, so the fallback is never silent.
                fields['receiver_reason'] = signal_problem(signal, target, time.time())[1] or 'receiver recovered'
            api.emit('waiting', url=pr['url'], head=pr['headRefOid'], ci=status,
                     pending_checks=[c['name'] for c in buckets.get('pending', [])],
                     unsettled_feedback=len(state.get('settling', {})), **fields)
            return
        delay = args.reconcile if active else args.interval
        deadlines = [delay, args.max_wait - elapsed]
        if state.get('settling'):
            deadlines.append(max(0, state['last_new_at'] + args.settle - now))
        elif status != 'pending':
            deadlines.append(max(0, state['quiet_since'] + args.quiet - now))
        until = time.monotonic() + min(deadlines)
        while time.monotonic() < until:
            time.sleep(min(1, max(0, until - time.monotonic())))
            new_generation, new_active = signal_status(signal, target, time.time())
            if (new_generation, new_active) != (generation, active):
                break
