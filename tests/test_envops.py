"""Behavior tests for the envops CLI, invoked as a subprocess."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / 'envops'

SRC_CONTENT = '''\
# app config
FOO=hello
BAR="quoted value"
export BAZ=exported
API_SECRET=sk-1234567890abcdefghij
DB_PASSWORD='p@ss w0rd!'
PLAIN_TOKEN=ghp_AbCdEfGhIjKlMnOpQrStUvWxYz123456
DEBUG=true
EMPTY=
'''


def run(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def src(tmp_path):
    path = tmp_path / 'src.env'
    path.write_text(SRC_CONTENT)
    return path


@pytest.fixture
def dest(tmp_path):
    path = tmp_path / 'dest.env'
    path.write_text('# existing dest\nFOO=old_foo\nKEEP_ME=untouched\n')
    return path


class TestShow:
    def test_lists_non_secret_values_in_clear(self, src):
        out = run('show', str(src)).stdout
        assert 'FOO=hello' in out
        assert 'DEBUG=true' in out

    def test_masks_secret_key_names(self, src):
        out = run('show', str(src)).stdout
        assert 'sk-1234567890abcdefghij' not in out
        assert 'p@ss w0rd!' not in out
        assert 'API_SECRET=' in out

    def test_masks_token_prefixed_values(self, src):
        out = run('show', str(src)).stdout
        assert 'ghp_AbCdEfGhIjKlMnOpQrStUvWxYz123456' not in out

    def test_masks_url_with_password(self, tmp_path):
        env = tmp_path / 'a.env'
        env.write_text('DATABASE_URL=postgres://user:hunter2@db:5432/app\n')
        out = run('show', str(env)).stdout
        assert 'hunter2' not in out

    def test_keys_filter(self, src):
        out = run('show', str(src), '-k', 'FOO', 'API_SECRET').stdout
        assert 'FOO=hello' in out
        assert 'DEBUG' not in out

    def test_keys_filter_still_masks(self, src):
        out = run('show', str(src), '-k', 'API_SECRET').stdout
        assert 'sk-1234567890abcdefghij' not in out

    def test_unsafe_exposes_values(self, src):
        out = run('show', str(src), '-k', 'API_SECRET', '--unsafe').stdout
        assert 'sk-1234567890abcdefghij' in out

    def test_missing_key_fails(self, src):
        result = run('show', str(src), '-k', 'NO_SUCH')
        assert result.returncode != 0

    def test_missing_file_fails(self, tmp_path):
        result = run('show', str(tmp_path / 'nope.env'))
        assert result.returncode != 0


class TestSecretDetection:
    """Regression cases from real project .env files"""

    # values that were falsely masked and must be shown in clear
    NON_SECRETS = {
        'BETTER_AUTH_URL': 'http://localhost:5173',
        'BETTER_AUTH_TELEMETRY': '0',
        'OPENAI_BASE_URL': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'FILECONV_BASE_URL': 'http://123.19.48.124/api/fileconv',
        'VITE_BACKEND_URL_FOR_DS': 'http://host.docker.internal:5173',
        'S3_ENDPOINT_FOR_ONLYOFFICE': 'http://host.docker.internal:9000',
        # bucket names: readable words joined by dashes, no random run
        'ALIYUN_BUCKET_SNAPSHOT_NAME': 'foobar-demo-snapshot',
        # bare hostnames without a scheme
        'ALIYUN_BUCKET_SNAPSHOT_ENDPOINT': 'oss-cn-beijing.aliyuncs.com',
        # long URL host made of word segments
        'USER_UPLOAD_BASE_URL': 'https://foobar-demo-user-upload.oss-cn-wulanchabu.aliyuncs.com',
        # db url with user but no password; db name has digits + underscores
        'DB_URL': 'mysql://cw@127.0.0.1:3306/foo_bar_demo_2024',
        # pure numbers are never secrets, even under a secret-looking key name
        'AUTH_TOKEN_EXPIRE': '604800',
        'REDIS_PASSWORD_RETRY_LIMIT': '3',
    }

    # same shape as the real secrets in those files; must stay masked
    SECRETS = {
        'BETTER_AUTH_SECRET': 'xK9Mq2vA7pl4wn8CT3bYc51',
        'ALIYUN_ACCESSKEY_SECRET': 'yoFakeAccessKeySecret1234mnVE',
        'DATABASE_URL': 'postgres://tb:hunter2@localhost:5432/tb',
        'SLACK_WEBHOOK': 'https://hooks.slack.com/services/T01CBCDFAGH/B02JALMNOKQ/x9YzAbCdEf12345qwerty',
        # config-suffixed key must not bypass the entropy net when the value embeds a token
        'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/services/T01ABCDEFGH/B02JKLENOPQ/x9YzAbCdEf12345qwerty',
        # entropy net: random token under an innocuous key name
        'RANDOM_BLOB': 'Zx9kQ2mP7vR4wN8jT3bY5cL1aD6f',
        # hex secret (letters + digits) must stay masked despite numeric-heavy look
        'AUTH_TOKEN_SECRET': '9c56198d2889486914ec2f068f16694bf61291f0b61d33975e79dec2f3ffa21f',
    }

    @pytest.fixture
    def env(self, tmp_path):
        path = tmp_path / 'tb.env'
        pairs = {**self.NON_SECRETS, **self.SECRETS}
        path.write_text(''.join(f'{k}={v}\n' for k, v in pairs.items()))
        return path

    @pytest.mark.parametrize('key', list(NON_SECRETS))
    def test_non_secret_shown_in_clear(self, env, key):
        out = run('show', str(env)).stdout
        assert f'{key}={self.NON_SECRETS[key]}' in out

    @pytest.mark.parametrize('key', list(SECRETS))
    def test_secret_stays_masked(self, env, key):
        out = run('show', str(env)).stdout
        assert self.SECRETS[key] not in out
        assert f'{key}=' in out


class TestUrlSegmentMasking:
    """URL-shaped values are masked per segment: the userinfo password is
    always masked, random-looking runs in path/query are masked, and the
    scheme, host, and port stay in the clear."""

    CASES = {
        # (raw value, expected display)
        'NEO4J_URL': (
            'neo4j://neo4j:123da5069e1e6093416d34cc@102.10.101.125:7687',
            'neo4j://neo4j:12******cc@102.10.101.125:7687',
        ),
        'DB_URL': (
            'mysql://root:UFuz4Tcyk4wzFDQ@mariadb:3306/dwtoolkit',
            'mysql://root:UF******DQ@mariadb:3306/dwtoolkit',
        ),
        # short password: masked without revealing head/tail
        'DATABASE_URL': (
            'postgres://tb:hunter2@localhost:5432/tb',
            'postgres://tb:******@localhost:5432/tb',
        ),
        # path token flagged by entropy; host and short path IDs stay clear
        'SLACK_WEBHOOK_URL': (
            'https://hooks.slack.com/services/T01ABCDEFGH/B02JKLMNOPQ/x9YzAbCdEf12345qwerty',
            'https://hooks.slack.com/services/T01ABCDEFGH/B02JKLMNOPQ/x9******ty',
        ),
        # no password, no random run: fully clear even under a secret-ish key
        'AUTH_REDIS_URL': (
            'redis://173.122.164.128:6379/3',
            'redis://173.122.164.128:6379/3',
        ),
    }

    @pytest.fixture
    def env(self, tmp_path):
        path = tmp_path / 'urls.env'
        path.write_text(''.join(f'{k}={raw}\n' for k, (raw, _) in self.CASES.items()))
        return path

    @pytest.mark.parametrize('key', list(CASES))
    def test_masks_only_secret_segments(self, env, key):
        out = run('show', str(env)).stdout
        assert f'{key}={self.CASES[key][1]}' in out

    def test_unsafe_shows_raw_url(self, env):
        out = run('show', str(env), '--unsafe').stdout
        for key, (raw, _) in self.CASES.items():
            assert f'{key}={raw}' in out


class TestListKeys:
    def test_prints_keys_only(self, src):
        out = run('list-keys', str(src)).stdout
        keys = out.splitlines()
        assert 'API_SECRET' in keys
        assert 'BAZ' in keys  # export prefix handled
        assert 'hello' not in out  # no values leaked


class TestCopy:
    def test_updates_and_adds_keys(self, src, dest):
        result = run('copy', str(src), str(dest), '-k', 'FOO', 'BAR')
        content = dest.read_text()
        assert 'FOO=hello' in content
        assert 'BAR="quoted value"' in content
        assert 'FOO' in result.stdout
        assert 'BAR' in result.stdout

    def test_preserves_unrelated_lines(self, src, dest):
        run('copy', str(src), str(dest), '-k', 'FOO')
        content = dest.read_text()
        assert 'KEEP_ME=untouched' in content
        assert '# existing dest' in content

    def test_untouched_keys_not_reported(self, src, dest):
        out = run('copy', str(src), str(dest), '-k', 'FOO').stdout
        assert 'KEEP_ME' not in out

    def test_noop_when_values_identical(self, src, dest):
        run('copy', str(src), str(dest), '-k', 'FOO')
        out = run('copy', str(src), str(dest), '-k', 'FOO').stdout
        assert 'no changes' in out

    def test_full_creates_dest_with_all_pairs(self, src, tmp_path):
        new_dest = tmp_path / 'new.env'
        result = run('copy', str(src), str(new_dest), '--full')
        content = new_dest.read_text()
        assert 'DEBUG=true' in content
        assert 'API_SECRET=sk-1234567890abcdefghij' in content
        # change report must mask the secret
        assert 'sk-1234567890abcdefghij' not in result.stdout

    def test_requires_keys_or_full(self, src, tmp_path):
        result = run('copy', str(src), str(tmp_path / 'd.env'))
        assert result.returncode != 0

    def test_keys_and_full_are_exclusive(self, src, tmp_path):
        result = run('copy', str(src), str(tmp_path / 'd.env'), '-k', 'FOO', '--full')
        assert result.returncode != 0

    def test_missing_source_key_fails(self, src, tmp_path):
        result = run('copy', str(src), str(tmp_path / 'd.env'), '-k', 'NO_SUCH_KEY')
        assert result.returncode != 0


class TestSet:
    def test_updates_existing_key_from_stdin(self, src):
        run('set', str(src), '-k', 'FOO', stdin='new value\n')
        assert 'FOO="new value"' in src.read_text()

    def test_appends_new_key(self, src):
        run('set', str(src), '-k', 'NEWKEY', stdin='no-trailing-newline')
        assert 'NEWKEY=no-trailing-newline' in src.read_text()

    def test_strips_single_trailing_newline(self, src):
        run('set', str(src), '-k', 'FOO', stdin='bare\n')
        assert run('read-value', str(src), '-K', 'FOO', '--unsafe').stdout == 'bare\n'

    def test_preserves_other_lines(self, src):
        run('set', str(src), '-k', 'FOO', stdin='x\n')
        content = src.read_text()
        assert '# app config' in content
        assert 'DEBUG=true' in content

    def test_output_masks_secret_value(self, src):
        out = run('set', str(src), '-k', 'MY_TOKEN', stdin='ghp_ZZZZYYYYXXXXWWWW1234\n').stdout
        assert 'ghp_ZZZZYYYYXXXXWWWW1234' not in out
        assert 'MY_TOKEN' in out


class TestReadValue:
    def test_prints_raw_value(self, src):
        result = run('read-value', str(src), '-K', 'API_SECRET', '--unsafe')
        assert result.stdout == 'sk-1234567890abcdefghij\n'

    def test_unquotes_value(self, src):
        result = run('read-value', str(src), '-K', 'BAR', '--unsafe')
        assert result.stdout == 'quoted value\n'

    def test_missing_key_fails(self, src):
        result = run('read-value', str(src), '-K', 'NO_SUCH', '--unsafe')
        assert result.returncode != 0

    def test_fails_without_unsafe_flag(self, src):
        result = run('read-value', str(src), '-K', 'FOO')
        assert result.returncode != 0
        assert '--unsafe' in result.stderr
        assert 'FOO' not in result.stdout

    def test_old_command_name_is_gone(self, src):
        result = run('unsafe-read-value', str(src), '-K', 'FOO')
        assert result.returncode != 0


FAKE_SSH = '''\
#!/bin/sh
# fake ssh for tests: `ssh <host> <command...>` runs the command in a local
# shell, so `host:/abs/path` arguments resolve to real files in tmp_path.
echo "$1" >> "$FAKE_SSH_LOG"
shift
exec sh -c "$*"
'''


@pytest.fixture
def remote(tmp_path):
    """Run envops with a fake `ssh` on PATH; remote paths map to local files."""
    bin_dir = tmp_path / 'fakebin'
    bin_dir.mkdir()
    fake_ssh = bin_dir / 'ssh'
    fake_ssh.write_text(FAKE_SSH)
    fake_ssh.chmod(0o755)
    log = tmp_path / 'ssh.log'

    def run_remote(*args, stdin=None):
        env = {
            **os.environ,
            'PATH': f'{bin_dir}:{os.environ["PATH"]}',
            'FAKE_SSH_LOG': str(log),
        }
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            cwd=tmp_path,
        )

    run_remote.log = log
    return run_remote


class TestRemoteSSH:
    """`[user@]host:/path` file arguments are read and written over ssh."""

    def test_copy_local_to_remote(self, src, dest, remote):
        result = remote('copy', str(src), f'foo@testhost:{dest}', '-k', 'FOO', 'BAR')
        assert result.returncode == 0
        content = dest.read_text()
        assert 'FOO=hello' in content
        assert 'BAR="quoted value"' in content
        assert 'foo@testhost' in remote.log.read_text()

    def test_copy_reports_changes_with_remote_dest_label(self, src, dest, remote):
        out = remote('copy', str(src), f'testhost:{dest}', '-k', 'FOO').stdout
        assert '~ FOO=hello (was old_foo)' in out
        assert f'testhost:{dest}' in out

    def test_copy_preserves_unrelated_remote_lines(self, src, dest, remote):
        remote('copy', str(src), f'testhost:{dest}', '-k', 'FOO')
        content = dest.read_text()
        assert 'KEEP_ME=untouched' in content
        assert '# existing dest' in content

    def test_copy_creates_missing_remote_dest(self, src, tmp_path, remote):
        new_dest = tmp_path / 'new.env'
        result = remote('copy', str(src), f'testhost:{new_dest}', '--full')
        assert result.returncode == 0
        assert 'DEBUG=true' in new_dest.read_text()

    def test_remote_write_preserves_permissions(self, src, dest, remote):
        dest.chmod(0o640)
        remote('copy', str(src), f'testhost:{dest}', '-k', 'FOO')
        assert dest.stat().st_mode & 0o777 == 0o640

    def test_remote_write_leaves_no_temp_files(self, src, dest, remote):
        remote('copy', str(src), f'testhost:{dest}', '-k', 'FOO')
        leftovers = [p.name for p in dest.parent.iterdir() if p.name.startswith('dest.env.')]
        assert leftovers == []

    def test_copy_noop_on_remote(self, src, dest, remote):
        remote('copy', str(src), f'testhost:{dest}', '-k', 'FOO')
        out = remote('copy', str(src), f'testhost:{dest}', '-k', 'FOO').stdout
        assert 'no changes' in out

    def test_remote_source_for_copy(self, src, dest, remote):
        result = remote('copy', f'testhost:{src}', str(dest), '-k', 'FOO')
        assert result.returncode == 0
        assert 'FOO=hello' in dest.read_text()

    def test_show_remote_masks_secrets(self, src, remote):
        out = remote('show', f'testhost:{src}').stdout
        assert 'FOO=hello' in out
        assert 'sk-1234567890abcdefghij' not in out

    def test_set_remote_key_from_stdin(self, src, remote):
        result = remote('set', f'testhost:{src}', '-k', 'FOO', stdin='new value\n')
        assert result.returncode == 0
        assert 'FOO="new value"' in src.read_text()

    def test_missing_remote_file_fails(self, tmp_path, remote):
        result = remote('show', f'testhost:{tmp_path}/nope.env')
        assert result.returncode != 0

    def test_local_paths_never_invoke_ssh(self, src, remote):
        result = remote('show', str(src))
        assert result.returncode == 0
        assert not remote.log.exists()
