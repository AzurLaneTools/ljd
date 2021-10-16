#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#


# We should visit stuff in it's execution order. That's important
from functools import lru_cache
import warnings

from ljd.ast.traverse import Visitor


@lru_cache()
def subclass_name_mapping(cls):
    mapping = {}
    for subcls in cls.__subclasses__():
        name = subcls.__name__
        if name in mapping:
            warnings.warn('Found duplicate class: %s %s', mapping[name], subcls)
        mapping[name] = subcls
        for subname, subsubcls in subclass_name_mapping(subcls).items():
            mapping[subname] = subsubcls
    return mapping


def to_dict(obj, visited=None):
    if visited is None:
        visited = set()
    if isinstance(obj, list):
        return [to_dict(item, visited) for item in obj]
    if not isinstance(obj, AstNode):
        return obj

    objid = id(obj)
    if objid in visited:
        return {'class': 'Ref', '_id': objid}
    visited.add(objid)

    d = {'class': obj.__class__.__name__, '_id': objid}
    for name in obj._slots:
        slot = getattr(obj, name, None)
        d[name] = to_dict(slot, visited)
    return d


def load_dict(data, mapping={}):
    if isinstance(data, list):
        return [load_dict(item, mapping) for item in data]
    if not isinstance(data, dict):
        return data
    cls_map = subclass_name_mapping(AstNode)
    data = data.copy()
    cls_name = data.pop('class')
    obj_id = data.pop('_id')
    if cls_name == 'Ref':
        return mapping[obj_id]
    subcls = cls_map[cls_name]
    mapping[obj_id] = res = subcls()
    for key in data:
        setattr(res, key, load_dict(data[key], mapping))
    return res


class AstNode(object):
    _slots = []

    def __str__(self) -> str:
        contains = []
        for key in self._slots:
            item = getattr(self, key, None)
            if isinstance(item, (StatementsList, list)):
                key = '%d %s' % (len(item), key)
            contains.append(key)
        if contains:
            contains = ': ' + ', '.join(contains)
        else:
            contains = ''
        return '%s(%s%s)' % (self.__class__.__name__, id(self), contains)

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, id(self))

    def to_dict(self):
        return to_dict(self)

    @staticmethod
    def load_dict(data):
        return load_dict(data)


class FunctionDefinition(AstNode):
    _slots = ['arguments', 'statements']

    def __init__(self):
        self.arguments = IdentifiersList()
        self.statements = StatementsList()

        self._upvalues = None
        self._debuginfo = None
        self._instructions_count = 0

        # If there was an exception parsing this function (eg, invalid bytecodes) and catch asserts is
        # enabled, the parsing error will be stored here and the rest of the function will be left empty.
        self.error = None

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_function_definition, self)

        visitor._visit(self.arguments)
        visitor._visit(self.statements)

        visitor._leave_node(visitor.leave_function_definition, self)

    def __str__(self) -> str:
        return 'FunctionDef(%s, %s)' % (self.arguments, self.statements)

    __repr__ = __str__


class Block(AstNode):
    _slots = ['index', 'first_address', 'last_address', 'contents', 'warp', 'loop']

    def __init__(self):
        self.index = -1
        self.warp = None
        self.contents = []
        self.first_address = 0
        self.last_address = 0
        self.warpins_count = 0
        self.loop = False

    def _accept(self, visitor: Visitor):
        visitor._visit_node(visitor.visit_block, self)

        visitor._visit_list(self.contents)
        visitor._visit(self.warp)

        visitor._leave_node(visitor.leave_block, self)

    def __str__(self):
        return (
            "{Block: {index: "
            + str(self.index)
            + ", warp: "
            + str(self.warp)
            + ", contents: "
            + str(self.contents)
            + ", first_address: "
            + str(self.first_address)
            + ", last_address: "
            + str(self.last_address)
            + ", warpins_count: "
            + str(self.warpins_count)
            + ", loop: "
            + str(self.loop)
            + "}}"
        )

    __repr__ = __str__


class TableConstructor(AstNode):
    _slots = ['array', 'records']
    anti_loop = set()
    cur_visitor = None

    def __init__(self):
        self.array = RecordsList()
        self.records = RecordsList()

    def _accept(self, visitor):
        if TableConstructor.cur_visitor is not None:
            if TableConstructor.cur_visitor != visitor:
                TableConstructor.cur_visitor = visitor
                TableConstructor.anti_loop.clear()
        else:
            TableConstructor.cur_visitor = visitor

        if self in TableConstructor.anti_loop:
            return

        TableConstructor.anti_loop.add(self)

        visitor._visit_node(visitor.visit_table_constructor, self)

        visitor._visit(self.array)
        visitor._visit(self.records)

        visitor._leave_node(visitor.leave_table_constructor, self)

    def __str__(self) -> str:
        return 'Table(...)'


class ArrayRecord(AstNode):
    _slots = ['value']

    def __init__(self):
        self.value = None

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_array_record, self)

        visitor._visit(self.value)

        visitor._leave_node(visitor.leave_array_record, self)


class TableRecord(AstNode):
    _slots = ['key', 'value']

    def __init__(self):
        self.key = None
        self.value = None

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_table_record, self)

        visitor._visit(self.key)
        visitor._visit(self.value)

        visitor._leave_node(visitor.leave_table_record, self)


class Assignment(AstNode):
    _slots = ['destinations', 'expressions']

    T_LOCAL_DEFINITION = 0
    T_NORMAL = 1

    def __init__(self):
        self.expressions = ExpressionsList()
        self.destinations = VariablesList()
        self.type = -1

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_assignment, self)

        visitor._visit(self.expressions)
        visitor._visit(self.destinations)

        visitor._leave_node(visitor.leave_assignment, self)

    def __str__(self):
        typ = ["LOCAL", "NORMAL"][self.type]
        return "Assignment<%s>(%s, %s)" % (typ, self.destinations, self.expressions)

    __repr__ = __str__


class BinaryOperator(AstNode):
    _slots = ['left', 'type', 'right']

    name_map = {
        0: 'or',
        10: 'and',
        20: 'lt',
        21: 'gt',
        22: 'le',
        23: 'ge',
        24: 'ne',
        25: 'eq',
        30: 'concat',
        40: 'add',
        41: 'subtract',
        50: 'multiply',
        51: 'divide',
        52: 'mod',
        70: 'pow',
    }
    T_LOGICAL_OR = 0  # left or right
    T_LOGICAL_AND = 10  # left and right

    T_LESS_THEN = 20  # left < right
    T_GREATER_THEN = 21  # left > right
    T_LESS_OR_EQUAL = 22  # left <= right
    T_GREATER_OR_EQUAL = 23  # left >= right

    T_NOT_EQUAL = 24  # left ~= right
    T_EQUAL = 25  # left == right

    T_CONCAT = 30  # left .. right

    T_ADD = 40  # left + right
    T_SUBTRACT = 41  # left - right

    T_MULTIPLY = 50  # left * right
    T_DIVISION = 51  # left / right
    T_MOD = 52  # left % right

    T_POW = 70  # left ^ right

    # Precedences are shared with UnaryOperator
    PR_OR = 1
    PR_AND = 2
    PR_COMPARISON = 3
    PR_CONCATENATE = 4
    PR_MATH_ADDSUB = 5
    PR_MATH = 6
    PR_UNARY = 7
    PR_EXPONENT = 8

    def __init__(self):
        self.type = -1
        self.left = None
        self.right = None

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_binary_operator, self)

        visitor._visit(self.left)
        visitor._visit(self.right)

        visitor._leave_node(visitor.leave_binary_operator, self)

    # Use this instead of the type field, as stuff like + and - have the same precedence this way
    def precedence(self):
        # Note that print(1 or 2 and false) prints 1
        if self.type <= self.T_LOGICAL_OR:
            return BinaryOperator.PR_OR

        elif self.type <= self.T_LOGICAL_AND:
            return BinaryOperator.PR_AND

        elif self.type <= self.T_EQUAL:
            return BinaryOperator.PR_COMPARISON

        elif self.type <= self.T_CONCAT:
            return BinaryOperator.PR_CONCATENATE

        elif self.type <= self.T_SUBTRACT:
            return BinaryOperator.PR_MATH_ADDSUB

        elif self.type <= self.T_MOD:
            return BinaryOperator.PR_MATH

        elif self.type <= self.T_POW:
            return BinaryOperator.PR_EXPONENT

        else:
            raise ValueError('invalid type %d' % self.type)

    def is_right_associative(self):
        if self.type == self.T_CONCAT:
            # Although this is right-associative per the Lua manual, since that
            #  doesn't matter here since `("a" .. "b") .. "c"` is the same as `"a" .. ("b" .. "c")`,
            #  LuaJIT doesn't consider it to be right-associative and thus groups it accordingly. Hence,
            #  setting this to True results in unnecessary braces being introduced.
            return False

        elif self.type == self.T_POW:
            return True

        else:
            return False

    def is_commutative(self):
        if self.type <= self.T_LOGICAL_AND:
            return True

        elif self.type <= self.T_GREATER_OR_EQUAL:
            return False

        elif self.type <= self.T_EQUAL:
            return True

        elif self.type <= self.T_CONCAT:
            return False

        elif self.type <= self.T_ADD:
            return True

        elif self.type <= self.T_SUBTRACT:
            return False

        elif self.type <= self.T_MULTIPLY:
            return True

        elif self.type <= self.T_MOD:
            return False

        elif self.type <= self.T_POW:
            return False

        else:
            assert False

    def __str__(self):
        op = self.name_map.get(self.type, self.type)
        return 'BinOp({} {} {})'.format(self.left, op, self.right)


class UnaryOperator(AstNode):
    _slots = ['type', 'operand']

    name_map = {60: 'not', 61: 'len', 62: 'minus', 63: 'str', 64: 'number'}
    T_NOT = 60  # not operand
    T_LENGTH_OPERATOR = 61  # #operand
    T_MINUS = 62  # -operand

    # Only available on bytecode revision 2 (LuaJIT 2.1)
    # This used to be if'd off so accessing it would be
    # an error, that is unfortunately no longer possible
    # due to the switchable version system.
    T_TOSTRING = 63  # tostring()
    T_TONUMBER = 64  # tonumber()

    def __init__(self):
        self.type = -1
        self.operand = None

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_unary_operator, self)

        visitor._visit(self.operand)

        visitor._leave_node(visitor.leave_unary_operator, self)

    def precedence(self):
        return BinaryOperator.PR_UNARY

    def __str__(self):
        op = self.name_map.get(self.type, self.type)
        return 'BinOp({} {})'.format(op, self.operand)


class StatementsList(AstNode):
    _slots = ['contents']

    def __init__(self):
        self.contents = []

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_statements_list, self)

        visitor._visit_list(self.contents)

        visitor._leave_node(visitor.leave_statements_list, self)

    def __str__(self):
        items = [str(c) for c in self.contents]
        return '%s(\n%s\n)' % (self.__class__.__name__, '\n'.join(items))

    __repr__ = __str__

    def __len__(self):
        return len(self.contents)


class IdentifiersList(StatementsList):
    def __init__(self):
        self.contents = []

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_identifiers_list, self)

        visitor._visit_list(self.contents)

        visitor._leave_node(visitor.leave_identifiers_list, self)


class RecordsList(StatementsList):
    def __init__(self):
        self.contents = []

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_records_list, self)

        visitor._visit_list(self.contents)

        visitor._leave_node(visitor.leave_records_list, self)


class VariablesList(StatementsList):
    def __init__(self):
        self.contents = []

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_variables_list, self)

        visitor._visit_list(self.contents)

        visitor._leave_node(visitor.leave_variables_list, self)


class ExpressionsList(StatementsList):
    def __init__(self):
        self.contents = []

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_expressions_list, self)

        visitor._visit_list(self.contents)

        visitor._leave_node(visitor.leave_expressions_list, self)


# Called Name in the Lua 5.1 reference
class Identifier(AstNode):
    _slots = ['name', 'type', 'slot', 'id']

    T_SLOT = 0
    T_LOCAL = 1
    T_UPVALUE = 2
    T_BUILTIN = 3

    def __init__(self):
        self.name = None
        self.type = -1
        self.slot = -1
        self.id = -1
        self._varinfo = None

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_identifier, self)
        visitor._leave_node(visitor.leave_identifier, self)

    def _slot_name(self):
        name = str(self.slot)
        if self.id != -1:
            name += "_" + str(self.id)
        else:
            slot_ids = getattr(self, "_ids", None)
            if slot_ids:
                for i, slot_id in enumerate(slot_ids):
                    name += "_" + str(slot_id)
        return name

    def __str__(self):
        if self.type == Identifier.T_SLOT:
            if self.name:
                name = ':' + self.name
            else:
                name = ''
            return "IdentSlot(%s%s)" % (self._slot_name(), name)

        if self.type == Identifier.T_BUILTIN:
            return "IdentBuiltin(%s)" % self.name

        return (
            "{ Identifier: {name: "
            + str(self.name)
            + ", type: "
            + ["T_SLOT", "T_LOCAL", "T_UPVALUE", "T_BUILTIN"][self.type]
            + ", slot: "
            + self._slot_name()
            + "} }"
        )

    __repr__ = __str__


# helper vararg/varreturn


class MULTRES(AstNode):
    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_multres, self)
        visitor._leave_node(visitor.leave_multres, self)


class GetItem(AstNode):
    _slots = ['table', 'key']

    def __init__(self):
        self.table = None
        self.key = None

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_table_element, self)

        visitor._visit(self.key)
        visitor._visit(self.table)

        visitor._leave_node(visitor.leave_table_element, self)

    def __str__(self):
        return str(self.table) + "[" + str(self.key) + "]"

    def __repr__(self):
        return "{0}@{1}".format(str(self.key), str(self.table))


class Vararg(AstNode):
    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_vararg, self)
        visitor._leave_node(visitor.leave_vararg, self)


class FunctionCall(AstNode):
    _slots = ['function', 'arguments', 'is_method']

    def __init__(self):
        self.function = None
        self.arguments = ExpressionsList()
        self.is_method = False

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_function_call, self)

        visitor._visit(self.arguments)
        visitor._visit(self.function)

        visitor._leave_node(visitor.leave_function_call, self)

    def __str__(self):
        return "FunctionCall(%s %s)" % (self.function, self.arguments)


class If(AstNode):
    _slots = ['expression', 'then_block', 'elseifs', 'else_block']

    def __init__(self):
        self.expression = None
        self.then_block = StatementsList()
        self.elseifs = []
        self.else_block = StatementsList()

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_if, self)

        visitor._visit(self.expression)
        visitor._visit(self.then_block)

        visitor._visit_list(self.elseifs)

        visitor._visit(self.else_block)

        visitor._leave_node(visitor.leave_if, self)


class ElseIf(AstNode):
    _slots = ['expression', 'then_block']

    def __init__(self):
        self.expression = None
        self.then_block = StatementsList()

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_elseif, self)

        visitor._visit(self.expression)
        visitor._visit(self.then_block)

        visitor._leave_node(visitor.leave_elseif, self)


# ##


class UnconditionalWarp(AstNode):
    _slots = ['type', 'target', 'is_uclo']

    T_JUMP = 0
    T_FLOW = 1

    def __init__(self):
        self.type = -1
        self.target = None
        self.is_uclo = False

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_unconditional_warp, self)

        # DO NOT VISIT self.target - warps are not part of the tree

        visitor._leave_node(visitor.leave_unconditional_warp, self)


class ConditionalWarp(AstNode):
    _slots = ['condition', 'true_target', 'false_target']

    def __init__(self):
        self.condition = None
        self.true_target = None
        self.false_target = None

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_conditional_warp, self)

        visitor._visit(self.condition)
        # DO NOT VISIT self.true_target - warps are not part of the tree
        # DO NOT VISIT self.false_target - warps are not part of the tree

        visitor._leave_node(visitor.leave_conditional_warp, self)


class IteratorWarp(AstNode):
    _slots = ['variables', 'controls', 'body', 'way_out']

    def __init__(self):
        self.variables = VariablesList()
        self.controls = ExpressionsList()
        self.body = None
        self.way_out = None

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_iterator_warp, self)

        visitor._visit(self.variables)
        visitor._visit(self.controls)
        # DO NOT VISIT self.body - warps are not part of the tree
        # DO NOT VISIT self.way_out - warps are not part of the tree

        visitor._leave_node(visitor.leave_iterator_warp, self)


class NumericLoopWarp(AstNode):
    _slots = ['index', 'controls', 'body', 'way_out']

    def __init__(self):
        self.index = Identifier()
        self.controls = ExpressionsList()
        self.body = None
        self.way_out = None

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_numeric_loop_warp, self)

        visitor._visit(self.index)
        visitor._visit(self.controls)
        # DO NOT VISIT self.body - warps are not part of the tree
        # DO NOT VISIT self.way_out - warps are not part of the tree

        visitor._leave_node(visitor.leave_numeric_loop_warp, self)


class EndWarp(AstNode):
    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_end_warp, self)
        visitor._leave_node(visitor.leave_end_warp, self)

    def __str__(self):
        return "EndWarp"

    __repr__ = __str__


# ##


class Return(AstNode):
    _slots = ['returns']

    def __init__(self):
        self.returns = ExpressionsList()

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_return, self)

        visitor._visit(self.returns)

        visitor._leave_node(visitor.leave_return, self)

    def __str__(self) -> str:
        return 'Return(%s)' % self.returns

    __repr__ = __str__


class Break(AstNode):
    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_break, self)
        visitor._leave_node(visitor.leave_break, self)


class While(AstNode):
    _slots = ['expression', 'statements']

    def __init__(self):
        self.expression = None
        self.statements = StatementsList()

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_while, self)

        visitor._visit(self.expression)
        visitor._visit(self.statements)

        visitor._leave_node(visitor.leave_while, self)


class RepeatUntil(AstNode):
    _slots = ['expression', 'statements']

    def __init__(self):
        self.expression = None
        self.statements = StatementsList()

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_repeat_until, self)

        visitor._visit(self.statements)
        visitor._visit(self.expression)

        visitor._leave_node(visitor.leave_repeat_until, self)


class NumericFor(AstNode):
    _slots = ['variable', 'expression', 'statements']

    def __init__(self):
        self.variable = None
        self.expressions = ExpressionsList()
        self.statements = StatementsList()

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_numeric_for, self)

        visitor._visit(self.variable)
        visitor._visit(self.expressions)
        visitor._visit(self.statements)

        visitor._leave_node(visitor.leave_numeric_for, self)


class IteratorFor(AstNode):
    _slots = ['expressions', 'expression', 'statements']

    def __init__(self):
        self.expressions = ExpressionsList()
        self.identifiers = VariablesList()
        self.statements = StatementsList()

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_iterator_for, self)

        visitor._visit(self.expressions)
        visitor._visit(self.identifiers)
        visitor._visit(self.statements)

        visitor._leave_node(visitor.leave_iterator_for, self)

    def __str__(self) -> str:
        return 'For(%s, %s, %s)' % (self.expressions, self.identifiers, self.statements)

    __repr__ = __str__


class Constant(AstNode):
    _slots = ['type', 'value']
    T_INTEGER = 0
    T_FLOAT = 1
    T_STRING = 2
    T_CDATA = 3

    def __init__(self):
        self.type = -1
        self.value = None

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_constant, self)
        visitor._leave_node(visitor.leave_constant, self)

    def __str__(self):
        return str(self.value)


class Primitive(AstNode):
    _slots = ['type']

    T_NIL = 0
    T_TRUE = 1
    T_FALSE = 2

    def __init__(self):
        self.type = -1

    def _accept(self, visitor):
        visitor._visit_node(visitor.visit_primitive, self)
        visitor._leave_node(visitor.leave_primitive, self)

    def __str__(self):
        return ["nil", "True", "False"][self.type]


class NoOp(AstNode):
    def _accept(self, visitor):
        pass
