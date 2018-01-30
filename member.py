from time import time


class Member:
    def __init__(self, nick, user=None, host=None):
        self.nick = nick
        self.user = user
        self.host = host

    def __str__(self):
        return '{}!{}@{}'.format(self.nick, self.user, self.host)

    def set(self, nick=None, user=None, host=None):
        if nick:
            self._set_nick(nick)
        if user:
            self._set_user(user)
        if host:
            self._set_host(host)

    def _set_nick(self, nick):
        self.nick = nick

    def _set_user(self, user):
        self.user = user

    def _set_host(self, host):
        self.host = host


class MemberList:
    def __init__(self, recent_until=10.00):
        self._members = set()
        self._recent = []
        self._recent_until = recent_until

    def __len__(self):
        return len(self._members)

    def __iter__(self):
        return self._members.__iter__()

    def add(self, nick, user=None, host=None):
        if not self.contains(nick=nick):
            m = Member(nick, user, host)
            self._members.add(m)
            self._recent.append((time(), m))
        else:
            member = self.__getitem__(nick)
            member.set(user=user, host=host)
        self._trim_recent()

    def remove(self, nick):
        member = self.__getitem__(nick)
        if not member:
            return
        self._members.discard(member)
        self._recent = [(at, m) for at, m in self._recent if m.nick != nick]
        self._trim_recent()

    def discard(self, nick):
        return self.remove(nick)

    def contains(self, nick=None, user=None, host=None):
        assert nick is not None or user is not None or host is not None

        match_nick, match_user, match_host = False, False, False

        if nick:
            match_nick = self._contains_nick(nick)
        if user:
            match_user = self._contains_user(user)
        if host:
            match_host = self._contains_host(host)

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

        return False

    def _contains_nick(self, nick):
        m = self.__getitem__(nick)
        return m if m else False

    def _contains_user(self, user):
        user = user.lower()
        for m in self:
            if m.user.lower() == user:
                return m
        return False

    def _contains_host(self, host):
        host = host.lower()
        for m in self:
            if m.host.lower() == host:
                return m
        return False

    def __getitem__(self, nick):
        nick = nick.lower()
        for m in self:
            if m.nick.lower() == nick:
                return m
        return None

    def matches(self, user=None, host=None):
        assert user is not None or host is not None
        matching_users = []
        matching_hosts = []
        if user:
            user = user.lower()
        if host:
            host = host.lower()
        for m in self:
            if user and m.user.lower() == user:
                matching_users.append(m)
            if host and m.host.lower() == host:
                matching_hosts.append(m)
        if user and host:
            return matching_users, matching_hosts
        if user:
            return matching_users
        return matching_hosts

    def _trim_recent(self):
        new_recent = []
        now = time()
        for at, m in self._recent:
            if at + self._recent_until >= now:
                new_recent.append((at, m))
        self._recent = new_recent

    def get_joined_since(self, t):
        members = set()
        for at, m in self._recent:
            if at >= t:
                members.add(m)
        return members
