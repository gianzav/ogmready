ogmready is a python library that is built upon
[owlready2](https://pypi.org/project/owlready2/) and strives to be an easy to
use Object-Graph Mapper, enabling the use of a Knowledge Graph based on an
Ontology as a viable alternative to relational databases. ogmready lets the user
define their domain classes and specify later how they should be mapped to
ontology concepts, leaving the application logic and the persistance strategy
decoupled.

# Quickstart

First, install the package:

```
pip install ogmready
```

Then define an Ontology, using owlready2 or your tool of choice:

```python
onto = owlready2.get_ontology("http://example.org/")

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

```

You can also add definitions under different namespaces:

```python
other_namespace = "http://other.org/"
with onto.get_namespace(other_namespace):
    class color(owlready2.DataProperty):
        range = [str]
```

Define your domain classes:

```python
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
```

And finally the mappers

```python
# Create a subclass of Mapper
class DogMapper(Mapper):
    # Specify the domain and ontology classes to perfom the mapping
    __source_class__ = Dog
    __target_class__ = ("Dog", "http://example.org/")

    # Define the mappings
    # Data property, functional by default
    id = DataPropertyMapping("id", primary_key=True),
    name = DataPropertyMapping("name"),

    # functional = False means that the property is a Set
    # we can pass a tuple (name, namespace) to say that a name is in a
    # different namespace than the default one
    colors = DataPropertyMapping(("color", other_namespace), functional=False)

class PersonMapper(Mapper):
    __source_class__ = Person
    __target_class__ = ("Person", "http://example.org")

    id = DataPropertyMapping("id", primary_key=True),
    name = DataPropertyMapping("name"),
    age = DataPropertyMapping("age"),
    # We can reference other object mappers
    dog = ObjectPropertyMapping("hasDog", DogMapper)
```

At this point, we can use the methods `from_owl` and `to_owl` of the mappers:

```python
# create the objects
d = Dog(1, "pluto", {"black", "white"})
p = Person(2, "mario", 10, d)

# create the mapper objects, passing the ontology as an argument
person_mapper = PersonMapper(onto)
dog_mapper = DogMapper(onto)

# map to owlready2 objects
onto_dog = dog_mapper.to_owl(d)
onto_person = person_mapper.to_owl(p)

# map back
p == person_mapper.from_owl(onto_person)
d == dog_mapper.from_owl(onto_dog)
```

# About lists

Since Knowledge Graph are usually stored in RDF format, which is based on
triples `<subject, predicate, object>`, storing lists is not straightforward.
While we use an OWL Ontology, we cannot use `rdf:List`, because it is used in the
OWL specification. A way around this is to use an Ontology that
lets us express the relations between lists and their elements: an example is
the [Collections
Ontology](https://github.com/collections-ontology/collections-ontology), which
defines the semantics of lists. To express something like `L = [a]`, using
the Collections Ontology we would say something like (mind that this is a
simplified RDF):

- `<L, is_a, List>`
- `<L, item, a_in_L>`
- `<a_in_L, is_a, ListItem>`
- `<a_in_L, index, 0>`
- `<a_in_L, itemContent, a>`

So `a_in_L` acts as a connecting object between `L` and its content `a`. An
intermediate element like `a_in_L` is needed because we could have more
occurrences of `a` inside of `L`. Moreover, with `index` we can express the
order of the elements.

In ogmready, an example could be (using `"http://purl.org/co/"`, the
Collections ontology):

```python
@dataclass
class Person:
    friends: List[Person]

co = "http://purl.org/co/"

class PersonMapper(Mapper):
    __source_class__ = Person
    __target_class__ = ("Person", "http://example.org/")

    # the parameters are:
    # - relation to connect list to items (e.g. 'item')
    # - OWL class of the connecting item (e.g. 'ListItem')
    # - relation to get to the actual item (e.g. 'itemContent')
    # - mapper for the item contents
    # - property to express the ordering of the elements
    friends = ListMapping(("item", co), ("ListItem", co), ("itemContent", co), PersonMapper, ("index", co))
```

# Defining your own mappings

It suffices to create a subclass of `Mapping` and implement the methods
`from_owl` and `to_owl`. The method `to_query` is relevant if the field that you
are mapping will be used in the queries to search for an already available
object in the ontology. The method `is_primary_key` by default returns `False`,
so changing its implementation makes sense if a property that you are mapping
could be a primary key, like `DataPropertyMapping`.

# A note on object retrieval

**TL;DR. It is always a good idea to specify a field as a primary key, if it is
possible**.

Since we could be mapping a deeply nested object, of course we don't want to
create new objects inside the Knowledge Graph if they are referenced by others
but are already storedy. By default, the `Mapper` class tries to search for the
referenced objects based on the fields that were specified as `primary_key`, but
in case no `primary_key` is defined, it defaults to a deep search (search of
_all_ object fields inside the Knowledge Graph), which could become slow and in
certain cases it could loop if there are circular references.

# Missing features (contributions are welcome!)

- [ ] Allowing the use of multiple mappers for a field, e.g. for `friend: Person
| Dog` it would be nice to say "use `PersonMapper` or `DogMapper`" based on
      what you find
