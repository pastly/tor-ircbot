def get_help_response(question):
    words = question.split(' ')
    words = [w.lower() for w in words]
    assert words[0] == 'help'
    words = words[1:]
    if len(words) < 1:
        return _clean_response_string(top_help_str)
    found, used_words, resp = _navigate_help_tree(words, help_)
    if not found:
        used_words = ['help']
        resp = top_help_str
    return _clean_response_string(resp)


def _clean_response_string(resp_str):
    ''' make sure there are no blank lines in the response, which would waste
    precious outbound messages '''
    broken = resp_str.split('\n')
    broken = [b for b in broken if len(b) > 0]
    return '\n'.join(broken)


def _navigate_help_tree(words, tree, used_words=['help']):
    assert len(words) > 0
    word = words[0]
    new_used_words = used_words + [word]
    remaining_words = words[1:]
    if word not in tree:
        return False, used_words, None
    assert 'str' in tree[word]
    assert 'subs' in tree[word]
    assert isinstance(tree[word]['subs'], dict) or tree[word]['subs'] is None
    if len(remaining_words) == 0:
        return True, new_used_words, tree[word]['str']
    if tree[word]['subs'] is None:
        return True, new_used_words, tree[word]['str']
    found, recursive_used_words, resp = _navigate_help_tree(
        remaining_words, tree[word]['subs'], new_used_words)
    if found:
        return found, recursive_used_words, resp
    return True, new_used_words, tree[word]['str']


help_akick_mask = '''Assuming person foo!~bar@baz.com ...
nick --> foo!*@* | user --> *!~bar@* | host --> *!*@baz.com
You can add an * before, after, or before and after to each of the above for a total of 12 valid masks.
For example: nick* --> foo*!*@*
'''


help_kick = '''Kick someone from the moderated channel(s)
kick <#channel|all> <nick>
examples:
    kick #foo annoyingdude
    kick all two1337foury0u
'''

help_ping = '''Respond with a pong message. A response means we\'re at least somewhat alive.
'''

help_mode = '''Change the mode of the moderated channel(s).
You may set arbitrary modes. Quiets and akicks are better done with their respective commands.
mode <#channel|all> <mode> [mode args]
examples:
    mode #foo +R
    mode all +io-v newoper!*@* novoicer!*@*
'''

help_help = '''Known commands: {comms}
Try "help ping"
'''

help_akick = '''{comm} someone from the moderated channel(s) via ChanServ.
Note you must remove {comm}s youself, if desired.
{comm} <#channel|all> <nick> <mask>[,mask[,...]] <reason str>
examples:
    {comm} #foo dude nick*,user having a lame nick
    {comm} all nsa host hacking users
see also: help {comm} mask'''

help_match = '''Search the moderated channel(s) for nicks that match the given nick's username or hostname.
match <nick>
Search the moderated channel(s) for nicks that match the given nickmask
match [*]<nick>[*]
examples:
    match freakydude
    match freak*
'''

help_ = {
    'help': {
        'str': help_help,
        'subs': None,
    },
    'kick': {
        'str': help_kick,
        'subs': None,
    },
    'akick': {
        'str': help_akick.format(comm='akick'),
        'subs': {
            'mask': {
                'str': help_akick_mask,
                'subs': None,
            },
        },
    },
    'quiet': {
        'str': help_akick.format(comm='quiet'),
        'subs': {
            'mask': {
                'str': help_akick_mask,
                'subs': None,
            },
        },
    },
    'ping': {
        'str': help_ping,
        'subs': None,
    },
    'mode': {
        'str': help_mode,
        'subs': None,
    },
    'match': {
        'str': help_match,
        'subs': None,
    },
}

help_['help']['str'] = help_['help']['str'].format(comms=' '.join(help_.keys()))
top_help_str = help_['help']['str']

# pylama:ignore=E501
