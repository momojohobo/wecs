from wecs.core import System
from wecs.core import and_filter
from wecs.core import or_filter
from wecs.rooms import Room
from wecs.rooms import RoomPresence
from wecs.rooms import ChangeRoomAction
from wecs.inventory import Inventory
from wecs.inventory import Takeable
from wecs.inventory import TakeAction
from wecs.inventory import DropAction
from wecs.inventory import TakeDropMixin

from components import Output
from components import Name
from components import Input
from components import TalkAction
from components import Dialogue
from components import Age
from components import Alive
from components import Dying
from components import Dead
from components import Undead
from components import Health
from components import Mana
from components import RejuvenationSpell
from components import RestoreHealthSpell
from components import LichdomSpell
from components import LichdomSpellEffect
from components import Action


# Used by ReadySpells
spells = [RejuvenationSpell, RestoreHealthSpell, LichdomSpell]


class Aging(System):
    entity_filters = {
        'has_age': and_filter([Age]),
        'grows_frail': and_filter([Age, Alive, Health]),
    }

    def update(self, filtered_entities):
        for entity in filtered_entities['has_age']:
            entity.get_component(Age).age += 1
        for entity in filtered_entities['grows_frail']:
            age = entity.get_component(Age).age
            age_of_frailty = entity.get_component(Age).age_of_frailty
            if age >= age_of_frailty:
                entity.get_component(Health).health -= 1


class RegenerateMana(System):
    entity_filters = {
        'has_mana': and_filter([Mana]),
    }

    def update(self, filtered_entities):
        for entity in filtered_entities['has_mana']:
            c = entity.get_component(Mana)
            if c.mana < c.max_mana:
                c.mana += 1


class ReadySpells(System):
    entity_filters = {
        'all_casters': and_filter([Mana]),
        'rejuvenation': and_filter([Mana, Age, Alive, RejuvenationSpell]),
        'restore_health': and_filter([
            and_filter([Mana, Health, RestoreHealthSpell]),
            or_filter([Alive, Undead]),
        ]),
        'lichdom': and_filter([Mana, Health, Alive, LichdomSpell]),
    }

    def update(self, filtered_entities):
        for entity in filtered_entities['all_casters']:
            entity.get_component(Mana).spells_ready = []

        for spell in spells:
            entities = filtered_entities[spell.name]
            for entity in entities:
                mana_cost = entity.get_component(spell).mana_cost
                if entity.get_component(Mana).mana >= mana_cost:
                    entity.get_component(Mana).spells_ready.append(spell.name)


class DieFromHealthLoss(System):
    entity_filters = {
        'is_living': and_filter([Health, Alive]),
    }

    def update(self, filtered_entities):
        for entity in set(filtered_entities['is_living']):
            if entity.get_component(Health).health <= 0:
                entity.remove_component(Alive)
                entity.add_component(Dying())


class BecomeLich(System):
    entity_filters = {
        'is_transforming': and_filter([Dying, LichdomSpellEffect]),
        'has_health': and_filter([Dying, LichdomSpellEffect, Health]),
    }

    def update(self, filtered_entities):
        transforming = set(filtered_entities['is_transforming'])
        has_health = set(filtered_entities['has_health'])
        for entity in transforming:
            print("LICHDOM SPELL TAKES EFFECT!")
            entity.remove_component(Dying)
            entity.remove_component(LichdomSpellEffect)
            entity.add_component(Undead())
        for entity in has_health:
            health = entity.get_component(Health)
            health.health = int(health.max_health / 2)


class Die(System):
    entity_filters = {
        'is_dying': and_filter([Dying]),
    }

    def update(self, filtered_entities):
        for entity in set(filtered_entities['is_dying']):
            entity.remove_component(Dying)
            entity.add_component(Dead())


class TextOutputMixin():
    def print_entity_state(self, entity):
        o = "" # Output accumulator

        # Name
        if entity.has_component(Name):
            name = entity.get_component(Name).name
        else:
            name = "Avatar"

        # Lifecycle status
        if entity.has_component(Alive):
            o += "{} is alive.\n".format(name)
        if entity.has_component(Dead):
            o += "{} is dead.\n".format(name)
        if entity.has_component(Undead):
            o += "{} is undead.\n".format(name)

        # Age
        if entity.has_component(Age):
            age = entity.get_component(Age).age,
            frailty = entity.get_component(Age).age_of_frailty,
            o += "{}'s age: ".format(name)
            o += "{}/{}".format(age, frailty)
            if age >= frailty:
                o += "(frail)"
            o += "\n"

        # Health
        if entity.has_component(Health):
            o += "{}'s health: {}/{}.\n".format(
                entity.get_component(Name).name,
                entity.get_component(Health).health,
                entity.get_component(Health).max_health,
            )

        # Mana
        if entity.has_component(Mana):
            o += "{}'s mana: {}/{}.\n".format(
                entity.get_component(Name).name,
                entity.get_component(Mana).mana,
                entity.get_component(Mana).max_mana,
            )

        # Castable spells
        if entity.has_component(Mana):
            o += "{} can cast: {}\n".format(
                entity.get_component(Name).name,
                ', '.join(entity.get_component(Mana).spells_ready),
            )

        # That's it about the avatar, now come its surroundings. If we
        # have written any text yet, let's add a readability newline.
        if o != "":
            o += "\n"

        # Presence in a room
        if entity.has_component(RoomPresence):
            # The room itself
            room_ref = entity.get_component(RoomPresence).room
            room = self.world.get_entity(room_ref)
            if not room.has_component(Name):
                o += "{} is in a nameless room\n".format(name)
            else:
                room_name = room.get_component(Name).name
                o += "{} is the room '{}'\n".format(name, room_name)

            # Other presences in the room
            presences = entity.get_component(RoomPresence).presences
            if presences:
                names = []
                for idx, presence in enumerate(presences):
                    present_entity = self.world.get_entity(presence)
                    if present_entity.has_component(Name):
                        names.append("({}) {}".format(
                            str(idx),
                            present_entity.get_component(Name).name,
                        ))
                o += "In the room are: {}\n".format(', '.join(names))

            # Adjacent rooms
            nearby_rooms = room.get_component(Room).adjacent
            nearby_room_names = []
            for idx, nearby_room in enumerate(nearby_rooms):
                nearby_room_entity = self.world.get_entity(nearby_room)
                if nearby_room_entity.has_component(Name):
                    nearby_room_names.append("({}) {}".format(
                        str(idx),
                        nearby_room_entity.get_component(Name).name,
                    ))
                else:
                    nearby_room_names.append("({}) (unnamed)".format(str(idx)))
            o += "Nearby rooms: {}\n".format(', '.join(nearby_room_names))

        # We're done, now let's get it on the screen.
        print(o)


class ShellMixin(TakeDropMixin):
    def shell(self, entity):
        if entity.has_component(Name):
            name = entity.get_component(Name).name
        else:
            name = "Avatar"
        query = "Command for {}: ".format(
            name,
        )
        while not self.run_command(input(query), entity):
            pass

    def run_command(self, command, entity):
        if command in ("i", "inventory"):
            self.show_inventory(entity)
            return False # Instant action
        elif command.startswith("take "):
            return self.take_command(entity, int(command[5:]))
        elif command.startswith("drop "):
            return self.drop_command(entity, int(command[5:]))
        elif command.startswith("go "):
            return self.change_room_command(entity, int(command[3:]))
        elif command.startswith("talk "):
            return self.talk_command(entity, int(command[5:]))
        else:
            # FIXME: Replace this by individual FooAction components.
            # Currently pending:
            # * SpellcastingMixin
            # * Individual spells
            entity.get_component(Action).plan = command
            return True
        print("Unknown command \"{}\"".format(command))
        return False

    def take_command(self, entity, object_id):
        if not entity.has_component(RoomPresence):
            print("Can't take objects from the roomless void.")
            return False
        presences = entity.get_component(RoomPresence).presences

        item = self.world.get_entity(presences[object_id])
        if self.can_take(item, entity):
            entity.add_component(TakeAction(item=item._uid))
            return True

        return False

    def drop_command(self, entity, object_id):
        # If I have an inventory...
        if not entity.has_component(Inventory):
            print("{} has no inventory.".format(name))
            return False

        inventory = entity.get_component(Inventory).contents
        item = self.world.get_entity(inventory[object_id])

        if self.can_drop(item, entity):
            entity.add_component(DropAction(item=item._uid))
            return True

        return False

    def change_room_command(self, entity, target_idx):
        if not entity.has_component(RoomPresence):
            print("You have no presence that could be somewhere.")
            return False

        room_e = self.world.get_entity(entity.get_component(RoomPresence).room)
        room = room_e.get_component(Room)
        if target_idx < 0 or target_idx > len(room.adjacent):
            print("No such room.")
            return False

        target = room.adjacent[target_idx]
        entity.add_component(ChangeRoomAction(room=target))
        return True

    def talk_command(self, entity, target_idx):
        # FIXME: Sooo many assumptions in this line...
        talker = entity.get_component(RoomPresence).presences[target_idx]
        entity.add_component(TalkAction(talker=talker))
        return True

    def show_inventory(self, entity):
        if entity.has_component(Name):
            name = entity.get_component(Name).name
        else:
            name = "Avatar"

        if not entity.has_component(Inventory):
            print("{} has no inventory.".format(name))
            return False

        # FIXME: try/except NoSuchUID:
        contents = [self.world.get_entity(e)
                    for e in entity.get_component(Inventory).contents]
        if len(contents) == 0:
            print("{}'s inventory is empty".format(name))
            return False

        content_names = []
        for idx, content in enumerate(contents):
            if content.has_component(Name):
                content_names.append(
                    "({}) {}".format(
                        str(idx),
                        content.get_component(Name).name,
                    )
                )
            else:
                content_names.append("({}) (unnamed)".format(str(idx)))

        for entry in content_names:
            print(entry)
        return True


class Shell(TextOutputMixin, ShellMixin, System):
    entity_filters = {
        'outputs': and_filter([Output]),
        'act': and_filter([Input])
    }

    def update(self, filtered_entities):
        outputters = filtered_entities['outputs']
        actors = filtered_entities['act']
        for entity in outputters:
            self.print_entity_state(entity)
            if entity in filtered_entities['act']:
                self.shell(entity)
        # Also give the actors without output a shell
        for entity in [e for e in actors if e not in outputters]:
            self.shell(entity)


class HaveDialogue(System):
    entity_filters = {
        'act': and_filter([TalkAction])
    }

    def update(self, filtered_entities):
        for entity in filtered_entities['act']:
            talker = self.world.get_entity(
                entity.get_component(TalkAction).talker,
            )

            # FIXME: Are they in the same room?

            if talker.has_component(Dialogue):
                if talker.has_component(Name):
                    print("> {} says: \"{}\"".format(
                        talker.get_component(Name).name,
                        talker.get_component(Dialogue).phrase,
                    ))
                else:
                    print("> " + talker.get_component(Dialogue).phrase)
            else:
                print("> \"...\"")
            entity.remove_component(TalkAction)


class SpellcastingMixin:
    def update(self, filtered_entities):
        for entity in filtered_entities['cast_spell']:
            if entity.get_component(Action).plan == self.spell_class.name:
                mana = entity.get_component(Mana)
                if self.spell_class.name in mana.spells_ready:
                    self.cast_spell(entity)
                else:
                    self.spell_not_ready(entity)


class CastRejuvenationSpell(System, SpellcastingMixin):
    entity_filters = {
        'cast_spell': and_filter([Action, Mana, RejuvenationSpell, Age, Alive]),
    }
    spell_class = RejuvenationSpell

    def update(self, filtered_entities):
        SpellcastingMixin.update(self, filtered_entities)

    def cast_spell(self, entity):
        mana = entity.get_component(Mana)
        spell = entity.get_component(self.spell_class)
        age = entity.get_component(Age)
        mana.mana -= spell.mana_cost
        age.age -= spell.time_restored
        if age.age < 0:
            age.age = 0
        print("REJUVENATION SPELL CAST!")
        entity.get_component(Action).plan = None

    def spell_not_ready(self, entity):
        entity.get_component(Action).plan = None


class CastRestoreHealthSpell(System, SpellcastingMixin):
    entity_filters = {
        'cast_spell': and_filter(
            [
                and_filter([Action, Mana, Health, RestoreHealthSpell]),
                or_filter([Alive, Undead]),
            ],
        ),
    }
    spell_class = RestoreHealthSpell

    def update(self, filtered_entities):
        SpellcastingMixin.update(self, filtered_entities)

    def cast_spell(self, entity):
        mana = entity.get_component(Mana)
        spell = entity.get_component(self.spell_class)
        age = entity.get_component(Age)
        health = entity.get_component(Health)

        mana.mana -= spell.mana_cost
        health.health += spell.health_restored
        if health.health > health.max_health:
            health.health = health.max_health
        print("RESTORE HEALTH CAST!")
        entity.get_component(Action).plan = None

    def spell_not_ready(self, entity):
        print("Not enough mana to restore health.")
        entity.get_component(Action).plan = None


class CastLichdomSpell(System, SpellcastingMixin):
    entity_filters = {
        'cast_spell': and_filter([Action, Mana, LichdomSpell, Alive]),
    }
    spell_class = LichdomSpell

    def update(self, filtered_entities):
        SpellcastingMixin.update(self, filtered_entities)

    def cast_spell(self, entity):
        mana = entity.get_component(Mana)
        spell = entity.get_component(self.spell_class)
        if entity.has_component(LichdomSpellEffect):
            mana.mana -= int(spell.mana_cost / 2)
            print("SPELL FAILS, already under its effect.")
        else:
            mana.mana -= spell.mana_cost
            entity.add_component(LichdomSpellEffect())
            print("LICHDOM SPELL CAST!")
        entity.get_component(Action).plan = None

    def spell_not_ready(self, entity):
        print("Not enough mana for lichdom spell.")
        entity.get_component(Action).plan = None
