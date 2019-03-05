# Copyright 2018 DeepMind Technologies Limited.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Functionality for working with probability spaces and random variables.

Basic recap of probability theory, and thus of classes in this file:

*   A probability space is a (finite or infinite) set Omega with a probability
    measure defined on this.
*   A random variable is a mapping from a probability space to another measure
    space.
*   An event is a measurable set in a sample space.

For example, suppose a bag contains 3 balls: two red balls, and one white ball.
This could be represented by a discrete probability space of size 3 with
elements {1, 2, 3}, with equal measure assigned to all 3 elements; and a random
variable that maps 1->red, 2->red, and 3->white. Then the probability of drawing
a red ball is the measure in the probability space of the inverse under the
random variable mapping of {red}, i.e., of {1, 2}, which is 2/3.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import abc
import itertools

# Dependency imports
import six
from six.moves import zip
import sympy


@six.add_metaclass(abc.ABCMeta)
class Event(object):
  """Represents an event in a measure space."""


@six.add_metaclass(abc.ABCMeta)
class ProbabilitySpace(object):
  """Represents a probability space."""

  @abc.abstractmethod
  def probability(self, event):
    """Returns the probability of an event."""


@six.add_metaclass(abc.ABCMeta)
class RandomVariable(object):
  """Random variable; a mapping from a probability space to a measure space."""

  @abc.abstractmethod
  def __call__(self, event):
    """Maps an `_Event` in the probability space to one in the sample space."""

  @abc.abstractmethod
  def inverse(self, event):
    """Maps event in the sample space back to the inverse in the prob. space."""


class DiscreteEvent(Event):
  """Set of discrete values."""

  def __init__(self, values):
    self._values = values

  @property
  def values(self):
    return self._values


class FiniteProductEvent(Event):
  """Event consisting of cartesian product of events."""

  def __init__(self, events):
    """Initializes a `FiniteProductEvent`.

    Args:
      events: Tuple of `Event`s; resulting event will be cartesian product of
          these.
    """
    self._events = events

  @property
  def events(self):
    return self._events

  def all_sequences(self):
    """Returns iterator of sequences by selecting a single event in each coord.

    This assumes that every component event is an instance of `DiscreteEvent`.

    Returns:
      Iterator over tuples of values.

    Raises:
      ValueError: If one of the component events is not a `DiscreteEvent`.
    """
    if not all(isinstance(event, DiscreteEvent) for event in self._events):
      raise ValueError('Not all component events are DiscreteEvents')
    values_list = [event.values for event in self._events]
    return itertools.product(*values_list)


class CountLevelSetEvent(Event):
  """Event of all sequences with fixed number of different values occurring."""

  def __init__(self, counts):
    """Initializes `CountLevelSetEvent`.

    E.g., to construct the event of getting two red balls and one green ball,
    pass `counts = {red: 2, green: 1}`. (Then `all_sequences()` would return
    `[(red, red, green), (red, green, red), (green, red, red)]`.

    Args:
      counts: Dictionary mapping values to the number of times they occur in a
          sequence.
    """
    self._counts = counts
    self._all_sequences = None

  @property
  def counts(self):
    return self._counts

  def all_sequences(self):
    """Returns all sequences generated by this level set."""
    if self._all_sequences is None:
      # Generate via dynamic programming.
      cache = {}  # dict mapping tuple -> list of tuples
      labels = list(self._counts.keys())

      def generate(counts):
        """Returns list of tuples for given `counts` of labels."""
        if sum(counts) == 0:
          return [()]
        counts = tuple(counts)
        if counts in cache:
          return cache[counts]
        generated = []
        for i, count in enumerate(counts):
          if count == 0:
            continue
          counts_minus = list(counts)
          counts_minus[i] -= 1
          counts_minus = tuple(counts_minus)
          extensions = generate(counts_minus)
          generated += [tuple([labels[i]] + list(extension))
                        for extension in extensions]
        cache[counts] = generated
        return generated

      self._all_sequences = generate(list(self._counts.values()))

    return self._all_sequences


class SequenceEvent(Event):
  """Collection of sequences."""

  def __init__(self, sequences):
    self._sequences = sequences

  def all_sequences(self):
    return self._sequences


def normalize_weights(weights):
  """Normalizes the weights (as sympy.Rational) in dictionary of weights."""
  weight_sum = sum(six.itervalues(weights))
  return {
      i: sympy.Rational(weight, weight_sum)
      for i, weight in six.iteritems(weights)
  }


class DiscreteProbabilitySpace(ProbabilitySpace):
  """Discrete probability space."""

  def __init__(self, weights=None):
    """Initializes an `DiscreteProbabilitySpace`.

    Args:
      weights: Dictionary mapping values to relative probability of selecting
          that value. This will be normalized.
    """
    self._weights = normalize_weights(weights)

  def probability(self, event):
    if isinstance(event, DiscreteEvent):
      return sum(self._weights[value]
                 for value in event.values if value in self._weights)
    else:
      raise ValueError('Unhandled event type {}'.format(type(event)))

  @property
  def weights(self):
    """Returns dictionary of probability of each element."""
    return self._weights


class FiniteProductSpace(ProbabilitySpace):
  """Finite cartesian product of probability spaces."""

  def __init__(self, spaces):
    """Initializes a `FiniteProductSpace`.

    Args:
      spaces: List of `ProbabilitySpace`.
    """
    self._spaces = spaces

  def all_spaces_equal(self):
    return all([self._spaces[0] == space for space in self._spaces])

  def probability(self, event):
    # Specializations for optimization.
    if isinstance(event, FiniteProductEvent):
      assert len(self._spaces) == len(event.events)
      return sympy.prod([
          space.probability(event_slice)
          for space, event_slice in zip(self._spaces, event.events)])

    if isinstance(event, CountLevelSetEvent) and self.all_spaces_equal():
      space = self._spaces[0]
      counts = event.counts
      probabilities = {
          value: space.probability(DiscreteEvent({value}))
          for value in six.iterkeys(counts)
      }

      num_events = sum(six.itervalues(counts))
      assert num_events == len(self._spaces)
      # Multinomial coefficient:
      coeff = (
          sympy.factorial(num_events) / sympy.prod(
              [sympy.factorial(i) for i in six.itervalues(counts)]))
      return coeff * sympy.prod([
          pow(probabilities[value], counts[value])
          for value in six.iterkeys(counts)
      ])

    raise ValueError('Unhandled event type {}'.format(type(event)))

  @property
  def spaces(self):
    """Returns list of spaces."""
    return self._spaces


class SampleWithoutReplacementSpace(ProbabilitySpace):
  """Probability space formed by sampling discrete space without replacement."""

  def __init__(self, weights, n_samples):
    """Initializes a `SampleWithoutReplacementSpace`.

    Args:
      weights: Dictionary mapping values to relative probability of selecting
          that value. This will be normalized.
      n_samples: Number of samples to draw.

    Raises:
      ValueError: If `n_samples > len(weights)`.
    """
    if n_samples > len(weights):
      raise ValueError('n_samples is more than number of discrete elements')
    self._weights = normalize_weights(weights)
    self._n_samples = n_samples

  @property
  def n_samples(self):
    """Number of samples to draw."""
    return self._n_samples

  def probability(self, event):
    try:
      all_sequences = event.all_sequences()
    except AttributeError:
      raise ValueError('Unhandled event type {}'.format(type(event)))

    probability_sum = 0
    for sequence in all_sequences:
      if len(sequence) != len(set(sequence)):
        continue  # not all unique, so not "without replacement".
      p_sequence = 1
      removed_prob = 0
      for i in sequence:
        p = self._weights[i] if i in self._weights else 0
        if p == 0:
          p_sequence = 0
          break
        p_sequence *= p / (1 - removed_prob)
        removed_prob += p
      probability_sum += p_sequence
    return probability_sum


class IdentityRandomVariable(RandomVariable):
  """Identity map of a probability space."""

  def __call__(self, event):
    return event

  def inverse(self, event):
    return event


class DiscreteRandomVariable(RandomVariable):
  """Specialization to discrete random variable.

  This is simply a mapping from a discrete space to a discrete space (dictionary
  lookup).
  """

  def __init__(self, mapping):
    """Initializes `DiscreteRandomVariable` from `mapping` dict."""
    self._mapping = mapping
    self._inverse = {}
    for key, value in six.iteritems(mapping):
      if value in self._inverse:
        self._inverse[value].add(key)
      else:
        self._inverse[value] = set([key])

  def __call__(self, event):
    if isinstance(event, DiscreteEvent):
      return DiscreteEvent({self._mapping[value] for value in event.values})
    else:
      raise ValueError('Unhandled event type {}'.format(type(event)))

  def inverse(self, event):
    if isinstance(event, DiscreteEvent):
      set_ = set()
      for value in event.values:
        if value in self._inverse:
          set_.update(self._inverse[value])
      return DiscreteEvent(set_)
    else:
      raise ValueError('Unhandled event type {}'.format(type(event)))


class FiniteProductRandomVariable(RandomVariable):
  """Product random variable.

  This has the following semantics. Let this be X = (X_1, ..., X_n). Then

  X(w) = (X_1(w_1), ..., X_n(w_n))

  (the sample space is assumed to be of sequence type).
  """

  def __init__(self, random_variables):
    """Initializes a `FiniteProductRandomVariable`.

    Args:
      random_variables: Tuple of `RandomVariable`.
    """
    self._random_variables = random_variables

  def __call__(self, event):
    if isinstance(event, FiniteProductEvent):
      assert len(event.events) == len(self._random_variables)
      zipped = list(zip(self._random_variables, event.events))
      return FiniteProductEvent(
          [random_variable(sub_event)
           for random_variable, sub_event in zipped])
    else:
      raise ValueError('Unhandled event type {}'.format(type(event)))

  def inverse(self, event):
    # Specialization for `FiniteProductEvent`; don't need to take all sequences.
    if isinstance(event, FiniteProductEvent):
      assert len(event.events) == len(self._random_variables)
      zipped = list(zip(self._random_variables, event.events))
      return FiniteProductEvent(tuple(
          random_variable.inverse(sub_event)
          for random_variable, sub_event in zipped))

    # Try fallback of mapping each sequence separately.
    try:
      all_sequences = event.all_sequences()
    except AttributeError:
      raise ValueError('Unhandled event type {}'.format(type(event)))

    mapped = set()
    for sequence in all_sequences:
      assert len(sequence) == len(self._random_variables)
      zipped = list(zip(self._random_variables, sequence))
      mapped_sequence = FiniteProductEvent(tuple(
          random_variable.inverse(DiscreteEvent({element}))
          for random_variable, element in zipped))
      mapped.update(mapped_sequence.all_sequences())
    return SequenceEvent(mapped)