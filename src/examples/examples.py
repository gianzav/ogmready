from typing import Set
from ogmready import Mapper, DataPropertyMapping, ObjectPropertyMapping, ListMapping
from dataclasses import dataclass
import owlready2


# ontology

onto = owlready2.get_ontology("http://example.org/")
other_namespace = "http://other.org/"

with onto:

    class Person(owlready2.Thing):
        pass

    class Dog(owlready2.Thing):
        pass

    class name(owlready2.DataProperty, owlready2.FunctionalProperty):
        range = [str]

    class age(owlready2.DataProperty, owlready2.FunctionalProperty):
        range = [int]

    class id(owlready2.DataProperty, owlready2.FunctionalProperty):
        range = [int]

    class hasDog(owlready2.ObjectProperty, owlready2.FunctionalProperty):
        domain = [Person]
        range = [Dog]


with onto.get_namespace(other_namespace):

    class color(owlready2.DataProperty):
        range = [str]


# domain classes


@dataclass
class Dog:
    id: int
    name: str
    colors: Set[str]


@dataclass
class Person:
    id: int
    name: str
    age: int
    dog: Dog


class DogMapper(Mapper):
    __source_class__ = Dog
    __target_class__ = ("Dog", "http://example.org/")

    id = DataPropertyMapping("id", primary_key=True)
    name = DataPropertyMapping("name")
    colors = DataPropertyMapping(("color", other_namespace), functional=False)


class PersonMapper(Mapper):
    __source_class__ = Person
    __target_class__ = ("Person", "http://example.org/")

    id = DataPropertyMapping("id", primary_key=True)
    name = DataPropertyMapping("name")
    age = DataPropertyMapping("age")
    dog = ObjectPropertyMapping("hasDog", DogMapper)


d = Dog(1, "pluto", {"black", "white"})
p = Person(2, "mario", 10, d)

person_mapper = PersonMapper(onto)
dog_mapper = DogMapper(onto)


onto_dog = dog_mapper.to_owl(d)
onto_person = person_mapper.to_owl(p)
