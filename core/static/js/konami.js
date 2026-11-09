// Up, up, down, down, left, right, left, right, b, a opens a fake homelab shell.
// Everything it prints is canned: this file is public, so keep real hostnames,
// IPs and anything else non-public out of it.
(() => {
    const CODE = [
        'arrowup', 'arrowup', 'arrowdown', 'arrowdown',
        'arrowleft', 'arrowright', 'arrowleft', 'arrowright', 'b', 'a',
    ].join();
    const PROMPT = 'guest@wielandtech:~$';

    const FILES = {
        'about.txt': 'Raphael. Likes adventure, learning, and production systems you can physically trip over.',
        'stack.txt': [
            'K3s, Flux v2, Traefik, MetalLB, Synology CSI, cert-manager,',
            'Sealed Secrets, CloudNativePG, Redis, Prometheus, Grafana.',
        ].join('\n'),
        'ursa.txt': 'Ursa: co-founder. Hard-working, easily bribed with praise.',
        'secrets.sealed': 'AgB3xY9...  Nice try. That is what the sealing is for.',
    };

    const PODS = [
        'NAME                       READY   STATUS             RESTARTS   AGE',
        'website-6f7c9d5b8-x2k4q    1/1     Running            0          2h',
        'postgres-1                 1/1     Running            0          41d',
        'redis-0                    1/1     Running            0          41d',
        'plex-5d8b7c6f4-m9t2z       1/1     Running            2          12d',
        'home-assistant-0           1/1     Running            1          12d',
        'grafana-84c6d7f9b-h7vqp    1/1     Running            0          9d',
        'n8n-7b9f6c8d5-r4wls        1/1     Running            0          9d',
        'free-time-0                0/1     CrashLoopBackOff   1337       3y',
    ].join('\n');

    const NEOFETCH = [
        'guest@wielandtech',
        '-----------------',
        'OS:          K3s on bare metal',
        'Nodes:       3',
        'GitOps:      Flux v2',
        'Ingress:     Traefik',
        'Storage:     Synology CSI',
        'Database:    CloudNativePG + Redis',
        'Monitoring:  Prometheus + Grafana',
        'Cost:        more than the cloud',
        'Reliability: less than the cloud',
        'Fun:         way more than the cloud',
    ].join('\n');

    const HELP = [
        'help               show this list',
        'whoami             who are you, really',
        'neofetch           about this machine',
        'ls                 list files',
        'cat <file>         print a file',
        'kubectl get pods   see what is running',
        'clear              clear the screen',
        'exit               back to the website (or press Esc)',
    ].join('\n');

    let overlay, output, input, returnFocus;
    const history = [];
    let historyIndex = 0;

    function print(text, className) {
        const line = document.createElement('div');
        line.textContent = text;
        if (className) {
            line.className = className;
        }
        output.appendChild(line);
    }

    function run(line) {
        const [command, ...args] = line.split(/\s+/);

        switch (command) {
            case '':
                break;
            case 'help':
                print(HELP);
                break;
            case 'whoami':
                print('guest. But you found the back door, so a very good one.');
                break;
            case 'neofetch':
                print(NEOFETCH);
                break;
            case 'ls':
                print(Object.keys(FILES).join('  '));
                break;
            case 'cat':
                if (!args.length) {
                    print('cat: which file? Try ls.', 'konami-error');
                } else if (Object.hasOwn(FILES, args[0])) {
                    print(FILES[args[0]]);
                } else {
                    print(`cat: ${args[0]}: No such file or directory`, 'konami-error');
                }
                break;
            case 'kubectl':
                if (args.join(' ') === 'get pods') {
                    print(PODS);
                } else {
                    print('error: guests only get "kubectl get pods"', 'konami-error');
                }
                break;
            case 'sudo':
                print('guest is not in the sudoers file. This incident will be reported to Ursa.', 'konami-error');
                break;
            case 'rm':
                print('rm: go ahead, Flux will just put it all back.', 'konami-error');
                break;
            case 'clear':
                output.textContent = '';
                break;
            case 'exit':
                close();
                break;
            default:
                print(`${command}: command not found. Try help.`, 'konami-error');
        }
    }

    function submit() {
        const line = input.value.trim();
        input.value = '';
        print(`${PROMPT} ${line}`, 'konami-echo');
        if (line) {
            history.push(line);
        }
        historyIndex = history.length;
        run(line);
        output.scrollTop = output.scrollHeight;
    }

    function recall(step) {
        const next = historyIndex + step;
        if (next < 0 || next > history.length) {
            return;
        }
        historyIndex = next;
        input.value = history[historyIndex] ?? '';
    }

    function onShellKeydown(e) {
        if (e.key === 'Escape') {
            close();
        } else if (e.key === 'Tab') {
            e.preventDefault();
        } else if (e.target === input && e.key === 'Enter') {
            // Without this, "exit" moves focus mid-keypress and Enter activates
            // whatever link the focus returned to.
            e.preventDefault();
            submit();
        } else if (e.target === input && e.key === 'ArrowUp') {
            e.preventDefault();
            recall(-1);
        } else if (e.target === input && e.key === 'ArrowDown') {
            e.preventDefault();
            recall(1);
        }
    }

    function build() {
        overlay = document.createElement('div');
        overlay.className = 'konami-overlay';
        overlay.addEventListener('keydown', onShellKeydown);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                close();
            } else if (!String(window.getSelection())) {
                input.focus();
            }
        });

        const terminal = document.createElement('div');
        terminal.className = 'konami-terminal';
        terminal.tabIndex = -1;
        terminal.setAttribute('role', 'dialog');
        terminal.setAttribute('aria-modal', 'true');
        terminal.setAttribute('aria-label', 'Homelab terminal easter egg');

        const title = document.createElement('div');
        title.className = 'konami-title';
        title.textContent = 'guest@wielandtech: ~';

        output = document.createElement('div');
        output.className = 'konami-output';
        output.setAttribute('aria-live', 'polite');

        const row = document.createElement('div');
        row.className = 'konami-row';

        const prompt = document.createElement('span');
        prompt.className = 'konami-prompt';
        prompt.textContent = PROMPT;

        input = document.createElement('input');
        input.className = 'konami-input';
        input.type = 'text';
        input.autocomplete = 'off';
        input.spellcheck = false;
        input.setAttribute('autocapitalize', 'off');
        input.setAttribute('aria-label', 'Shell command');

        row.append(prompt, input);
        terminal.append(title, output, row);
        overlay.appendChild(terminal);
        document.body.appendChild(overlay);

        print('Access granted. Welcome to the homelab.');
        print('Type help to look around.');
    }

    function open() {
        if (!overlay) {
            build();
        } else if (!overlay.hidden) {
            return;
        }
        returnFocus = document.activeElement;
        overlay.hidden = false;
        input.focus();
        output.scrollTop = output.scrollHeight;
    }

    function close() {
        overlay.hidden = true;
        returnFocus?.focus({ preventScroll: true });
    }

    // The theme toggle is a checkbox: having just clicked it shouldn't block the code.
    const TYPING_FIELDS = 'input:not([type=checkbox]), textarea, select, [contenteditable]';
    let pressed = [];

    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey || e.metaKey || e.altKey || e.target.closest?.(TYPING_FIELDS)) {
            return;
        }
        pressed = [...pressed, String(e.key).toLowerCase()].slice(-10);
        if (pressed.join() === CODE) {
            // Without this, the final "a" lands in the shell input focused below.
            e.preventDefault();
            pressed = [];
            open();
        }
    });
})();
