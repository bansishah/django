import datetime
from operator import attrgetter

from django.db import models
from django.contrib.multicolumn.models import ForeignKeyEx
from django.test import TestCase

class Country(models.Model):
    name = models.CharField(max_length=50)

    def __unicode__(self):
        return self.name


class Person(models.Model):
    name = models.CharField(max_length=128)
    person_country = ForeignKeyEx(Country)
    friends = models.ManyToManyField('self', through='Friendship', symmetrical=False)

    class Meta:
        ordering = ('name',)

    def __unicode__(self):
        return self.name

class Group(models.Model):
    name = models.CharField(max_length=128)
    group_country = ForeignKeyEx(Country)
    members = models.ManyToManyField(Person, related_name='groups', through='Membership')

    class Meta:
        ordering = ('name',)

    def __unicode__(self):
        return self.name


class Membership(models.Model):
    membership_country = ForeignKeyEx(Country)
    person = ForeignKeyEx(Person, include_related=[('membership_country', 'person_country')])
    group = ForeignKeyEx(Group, include_related=[('membership_country', 'group_country')])
    date_joined = models.DateTimeField(default=datetime.datetime.now)
    invite_reason = models.CharField(max_length=64, null=True)

    class Meta:
        ordering = ('date_joined', 'invite_reason')

    def __unicode__(self):
        return "%s is a member of %s" % (self.person.name, self.group.name)


class Friendship(models.Model):
    from_friend_country = ForeignKeyEx(Country, related_name="from_friend_country")
    from_friend = ForeignKeyEx(Person, include_related=[('from_friend_country', 'person_country')], related_name="from_friend")
    to_friend_country = ForeignKeyEx(Country, related_name="to_friend_country")
    to_friend = ForeignKeyEx(Person, include_related=[('to_friend_country', 'person_country')], related_name="to_friend")


class MultiColumnFKTests(TestCase):
    def setUp(self):
        # Creating countries
        self.usa = Country.objects.create(name="United States of America")
        self.soviet_union = Country.objects.create(name="Soviet Union")

        # Creating People
        self.bob = Person.objects.create(name='Bob', person_country=self.usa)
        self.jim = Person.objects.create(name='Jim', person_country=self.usa)
        self.george = Person.objects.create(name='George', person_country=self.usa)

        self.jane = Person.objects.create(name='Jane', person_country=self.soviet_union)
        self.mark = Person.objects.create(name='Mark', person_country=self.soviet_union)
        self.sam = Person.objects.create(name='Sam', person_country=self.soviet_union)

        # Creating Groups
        self.kgb = Group.objects.create(name='KGB', group_country=self.soviet_union)
        self.cia = Group.objects.create(name='CIA', group_country=self.usa)
        self.republican = Group.objects.create(name='Republican', group_country=self.usa)
        self.democrat = Group.objects.create(name='Democrat', group_country=self.usa)

    def test_get_succeeds_on_multicolumn_match(self):
        # Membership objects have access to their related Person if both country_ids match between them
        membership = Membership.objects.create(membership_country_id=self.usa.id, person_id=self.bob.id, group_id=self.cia.id)

        person = membership.person
        self.assertEqual((person.id, person.name), (self.bob.id, "Bob"))

    def test_get_fails_on_multicolumn_mismatch(self):
        # Membership objects returns DoesNotExist error when the there is no Person with the same id and country_id
        membership = Membership.objects.create(membership_country_id=self.usa.id, person_id=self.jane.id, group_id=self.cia.id)

        self.assertRaises(Person.DoesNotExist, getattr, membership, 'person')

    def test_reverse_query_returns_correct_result(self):
        # Creating a valid membership because it has the same country has the person
        Membership.objects.create(membership_country_id=self.usa.id, person_id=self.bob.id, group_id=self.cia.id)

        # Creating an invalid membership because it has a different country has the person
        Membership.objects.create(membership_country_id=self.soviet_union.id, person_id=self.bob.id, group_id=self.republican.id)

        self.assertQuerysetEqual(
            self.bob.membership_set.all(),[
                self.cia.id
            ],
            attrgetter("group_id")
        )

    def test_query_filters_correctly(self):

        # Creating a to valid memberships
        Membership.objects.create(membership_country_id=self.usa.id, person_id=self.bob.id, group_id=self.cia.id)
        Membership.objects.create(membership_country_id=self.usa.id, person_id=self.jim.id, group_id=self.cia.id)
        
        # Creating an invalid membership
        Membership.objects.create(membership_country_id=self.soviet_union.id, person_id=self.george.id, group_id=self.cia.id)

        self.assertQuerysetEqual(
            Membership.objects.filter(person__name__contains='o'),[
                self.bob.id
            ],
            attrgetter("person_id")
        )

    def test_reverse_query_filters_correctly(self):

        timemark = datetime.datetime.utcnow()
        timedelta = datetime.timedelta(days=1)

        # Creating a to valid memberships
        Membership.objects.create(membership_country_id=self.usa.id, person_id=self.bob.id, group_id=self.cia.id, date_joined=timemark - timedelta)
        Membership.objects.create(membership_country_id=self.usa.id, person_id=self.jim.id, group_id=self.cia.id, date_joined=timemark + timedelta)
        
        # Creating an invalid membership
        Membership.objects.create(membership_country_id=self.soviet_union.id, person_id=self.george.id, group_id=self.cia.id, date_joined=timemark + timedelta)

        self.assertQuerysetEqual(
            Person.objects.filter(membership__date_joined__gte=timemark),[
                'Jim'
            ],
            attrgetter('name')
        )

    def test_select_related_foreignkey_forward_works(self):
        Membership.objects.create(membership_country=self.usa, person=self.bob, group=self.cia)
        Membership.objects.create(membership_country=self.usa, person=self.jim, group=self.democrat)

        with self.assertNumQueries(1):
            people = [m.person for m in Membership.objects.select_related('person')]

        normal_people = [m.person for m in Membership.objects.all()]
        self.assertEqual(people, normal_people)

    def test_prefetch_foreignkey_forward_works(self):
        Membership.objects.create(membership_country=self.usa, person=self.bob, group=self.cia)
        Membership.objects.create(membership_country=self.usa, person=self.jim, group=self.democrat)

        with self.assertNumQueries(2):
            people = [m.person for m in Membership.objects.prefetch_related('person')]

        normal_people = [m.person for m in Membership.objects.all()]
        self.assertEqual(people, normal_people)

    def test_prefetch_foreignkey_reverse_works(self):
        Membership.objects.create(membership_country=self.usa, person=self.bob, group=self.cia)
        Membership.objects.create(membership_country=self.usa, person=self.jim, group=self.democrat)
        with self.assertNumQueries(2):
            membership_sets = [list(p.membership_set.all()) for p in Person.objects.prefetch_related('membership_set')]

        normal_membership_sets = [list(p.membership_set.all()) for p in Person.objects.all()]
        self.assertEqual(membership_sets, normal_membership_sets)

    def test_m2m_through_forward_returns_valid_members(self):
        # We start out by making sure that the Group 'CIA' has no members.
        self.assertQuerysetEqual(
            self.cia.members.all(),
            []
        )

        m1 = Membership.objects.create(membership_country=self.usa, person=self.bob, group=self.cia)
        m2 = Membership.objects.create(membership_country=self.usa, person=self.jim, group=self.cia)

        # Let's check to make sure that it worked.  Bob and Jim should be members of the CIA.

        self.assertQuerysetEqual(
            self.cia.members.all(), [
                'Bob',
                'Jim'
            ],
            attrgetter("name")
        )

    def test_m2m_through_reverse_returns_valid_members(self):
        # We start out by making sure that Bob is in no groups.
        self.assertQuerysetEqual(
            self.bob.groups.all(),
            []
        )

        m1 = Membership.objects.create(membership_country=self.usa, person=self.bob, group=self.cia)
        m2 = Membership.objects.create(membership_country=self.usa, person=self.bob, group=self.republican)


        # Bob should be in the CIA and a Republican
        self.assertQuerysetEqual(
            self.bob.groups.all(), [
                'CIA',
                'Republican'
            ],
            attrgetter("name")
        )

    def test_m2m_through_forward_ignores_invalid_members(self):
        # We start out by making sure that the Group 'CIA' has no members.
        self.assertQuerysetEqual(
            self.cia.members.all(),
            []
        )

        # Something adds jane to group CIA but Jane is in Soviet Union which isn't CIA's country
        m1 = Membership.objects.create(membership_country=self.usa, person=self.jane, group=self.cia)

        # There should still be no members in CIA
        self.assertQuerysetEqual(
            self.cia.members.all(),
            []
        )

    def test_m2m_through_reverse_ignores_invalid_members(self):
        # We start out by making sure that Jane has no groups.
        self.assertQuerysetEqual(
            self.jane.groups.all(),
            []
        )

        # Something adds jane to group CIA but Jane is in Soviet Union which isn't CIA's country
        m1 = Membership.objects.create(membership_country=self.usa, person=self.jane, group=self.cia)

        # Jane should still not be in any groups
        self.assertQuerysetEqual(
            self.jane.groups.all(),
            []
        )

    def test_m2m_through_on_self_works(self):
        self.assertQuerysetEqual(
            self.jane.friends.all(),
            []
        )

        Friendship.objects.create(from_friend_country=self.jane.person_country, from_friend=self.jane,
            to_friend_country=self.george.person_country, to_friend=self.george)

        self.assertQuerysetEqual(
            self.jane.friends.all(),
            ['George'],
            attrgetter("name")
        )

    def test_m2m_through_on_self_ignores_mismatch_columns(self):
        self.assertQuerysetEqual(
            self.jane.friends.all(),
            []
        )

        Friendship.objects.create(to_friend_country=self.jane.person_country, from_friend=self.jane,
            from_friend_country=self.george.person_country, to_friend=self.george)

        self.assertQuerysetEqual(
            self.jane.friends.all(),
            []
        )

    def test_prefetch_related_m2m_foward_works(self):
        Membership.objects.create(membership_country=self.usa, person=self.bob, group=self.cia)
        Membership.objects.create(membership_country=self.usa, person=self.jim, group=self.democrat)

        with self.assertNumQueries(2):
            members_lists = [list(g.members.all()) for g in Group.objects.prefetch_related('members')]

        normal_members_lists = [list(g.members.all()) for g in Group.objects.all()]
        self.assertEqual(members_lists, normal_members_lists)

    def test_prefetch_related_m2m_reverse_works(self):
        Membership.objects.create(membership_country=self.usa, person=self.bob, group=self.cia)
        Membership.objects.create(membership_country=self.usa, person=self.jim, group=self.democrat)

        with self.assertNumQueries(2):
            groups_lists = [list(p.groups.all()) for p in Person.objects.prefetch_related('groups')]

        normal_groups_lists = [list(p.groups.all()) for p in Person.objects.all()]
        self.assertEqual(groups_lists, normal_groups_lists)
