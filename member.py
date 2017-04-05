class Member:
    def __init__(self, nick, user=None, host=None):
        self._nick = nick
        self._user = user
        self._host = host

    def __str__(self):
        return '{}!{}@{}'.format(self._nick, self._user, self._host)

    def set(self, nick=None, user=None, host=None):
        if nick: self.__set_nick(nick)
        if user: self.__set_user(user)
        if host: self.__set_host(host)

    def __set_nick(self, nick):
        self._nick = nick

    def __set_user(self, user):
        self._user = user

    def __set_host(self, host):
        self._host = host

class MemberList:
    def __init__(self):
        self._members = set()

    def __len__(self):
        return len(self._members)

    def __iter__(self):
        return self._members.__iter__()

    def add(self, nick, user=None, host=None):
        if not self.contains(nick=nick):
            self._members.add(Member(nick, user, host))
        else:
            member = self.__getitem__(nick)
            member.set(user=user, host=host)

    def remove(self, nick):
        member = self.__getitem__(nick)
        if not member: return
        self._members.discard(member)

    def discard(self, nick):
        return self.remove(nick)

    def contains(self, nick=None, user=None, host=None):
        if nick:
            match_nick = self.__contains_nick(nick)
        if user:
            match_user = self.__contains_user(user)
        if host:
            match_host = self.__contains_host(host)

        if nick and not user and not host:
            return True if match_nick else False
        if user and not nick and not host:
            return True if match_user else False
        if host and not nick and not user:
            return True if match_host else False

        if nick and user and not host:
            return True if match_nick == match_user and match_nick else False
        if nick and host and not user:
            return True if match_nick == match_host and match_nick else False
        if user and host and not nick:
            return True if match_user == match_host and match_user else False

        if match_nick == match_user and match_nick == match_host:
            return True if match_nick else False

    def __contains_nick(self, nick):
        m = self.__getitem__(nick)
        return True if m else False

    def __contains_user(self, user):
        user = user.lower()
        for m in self._members:
            if m._user.lower() == user: return m
        return False

    def __contains_host(self, host):
        host = host.lower()
        for m in self._members:
            if m._host.lower() == host: return m
        return False

    def __getitem__(self, nick):
        nick = nick.lower()
        for m in self._members:
            if m._nick.lower() == nick: return m
        return None