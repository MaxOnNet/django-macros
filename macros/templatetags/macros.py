# Based on snippet by
# Author: Michal Ludvig <michal@logix.cz>
#         http://www.logix.cz/michal
#
# modified for args and kwargs by Skylar Saveland http://skyl.org
#
# updated for django 1.6, modified, and packaged by Nicholas Lourie,
# while working for kozbox, llc. http://kozbox.com

""" Macros.py, part of django-macros, allows for creation of
macros within django templates.
"""

from re import match as regex_match
from django import template
from django.template import FilterExpression
from django.template.loader import get_template
 
register = template.Library()
 
 
def _setup_macros_dict(parser):
    """ initiates the _macros attribute on the parser
    object, allowing for storage of the macros in the parser.
    """
    ## Each macro is stored in a new attribute
    ## of the 'parser' class. That way we can access it later
    ## in the template when processing 'use_macro' tags.
    try:
        # don't overwrite the attribute if it already exists
        parser._macros
    except AttributeError:
        parser._macros = {}
 
 
class DefineMacroNode(template.Node):
    """ The node object for the tag which
    defines a macro.
    """
    def __init__(self, name, nodelist, args, kwargs):
 
        self.name = name
        self.nodelist = nodelist
        self.args = args
        self.kwargs = kwargs
 
    def render(self, context):
        ## empty string - {% macro %} tag has no output
        return ''
 
 
@register.tag(name="macro")
def do_macro(parser, token):
    """ the function taking the parsed tag and returning
    a DefineMacroNode object.
    """
    try:
        bits = token.split_contents()
        tag_name, macro_name, arguments = bits[0], bits[1], bits[2:]
    except IndexError:
        raise template.TemplateSyntaxError(
            "'{0}' tag requires at least one argument (macro name)".format(
            token.contents.split()[0]))
    
    # use regex's to parse the arguments into arg
    # and kwarg definitions

    # the regex for identifying python variable names is:
    ##  r'^[A-Za-z_][\w_]*$'

    # args must be proper python variable names
    ## we'll want to capture it from the regex also.
    arg_regex = r'^([A-Za-z_][\w_]*)$'

    # kwargs must be proper variable names with a
    # default value, name="value",
    ## we'll want to capture the name and value from
    ## the regex as well.
    kwarg_regex = r'^([A-Za-z_][\w_]*)=(".*"|{0}.*{0})$'.format("'")

    args = []
    kwargs = {}
    for argument in arguments:
        arg_match = regex_match(
            arg_regex, argument)
        if arg_match:
            args.append(arg_match.groups()[0])
        else:
            kwarg_match = regex_match(
                kwarg_regex, argument)
            if kwarg_match:
                kwargs[kwarg_match.groups()[0]] = (
                    # remove the quotes from the value
                    kwarg_match.groups()[1])
            else:
                raise template.TemplateSyntaxError(
                    "Malformed arguments to the {0} tag.".format(
                        tag_name))
    
    # parse to the endmacro tag and get the contents
    nodelist = parser.parse(('endmacro', ))
    parser.delete_first_token()
 
    # store macro in parser._macros, creating attribute
    # if necessary
    _setup_macros_dict(parser)
    parser._macros[macro_name] = DefineMacroNode(
        macro_name, nodelist, args, kwargs)
    return parser._macros[macro_name]
 
 
class LoadMacrosNode(template.Node):
    """ The template tag node for loading macros from
    an external sheet.
    """
    def render(self, context):
        ## empty string - {% loadmacros %} tag does no output
        return ''
 
 
@register.tag(name="loadmacros")
def do_loadmacros(parser, token):
    """ The function taking a parsed tag and returning
    a LoadMacrosNode object, while also loading the macros
    into the page.
    """
    try:
        tag_name, filename = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError(
            "'{0}' tag requires at least one argument (macro name)".format(
            token.contents.split()[0]))
    if filename[0] in ('"', "'") and filename[-1] == filename[0]:
        filename = filename[1:-1]
    else:
        raise template.TemplateSyntaxError(
            "Malformed argument to the {0} template tag.".format(tag_name) +
            " Argument must be in quotes.")
    t = get_template(filename)
    macros = t.nodelist.get_nodes_by_type(DefineMacroNode)
    # make sure the _macros attribute dictionary is instantiated
    # on the parser, then add the macros to it.
    _setup_macros_dict(parser)
    for macro in macros:
        parser._macros[macro.name] = macro
    return LoadMacrosNode()
 
 
class UseMacroNode(template.Node):
    """ Template tag Node object for the tag which
    uses a macro.
    """
 
    def __init__(self, macro, fe_args, fe_kwargs):
        self.macro = macro
        self.fe_args = fe_args
        self.fe_kwargs = fe_kwargs
 
    def render(self, context):
 
        for i, arg in enumerate(self.macro.args):
            try:
                fe = self.fe_args[i]
                context[arg] = fe.resolve(context)
            except IndexError:
                context[arg] = ""
 
        for name, default in self.macro.kwargs.iteritems():
            if name in self.fe_kwargs:
                context[name] = self.fe_kwargs[name].resolve(context)
            else:
                context[name] = FilterExpression(default,
                                                 self.macro.parser
                ).resolve(context)
 
        return self.macro.nodelist.render(context)
 
 
@register.tag(name="use_macro")
def do_usemacro(parser, token):
    """ The function taking a parsed template tag
    and returning a UseMacroNode.
    """
    try:
        bits = token.split_contents()
        tag_name, macro_name, values = bits[0], bits[1], bits[2:]
    except IndexError:
        raise template.TemplateSyntaxError(
            "{0} tag requires at least one argument (macro name)".format(
                token.contents.split()[0]))
    try:
        macro = parser._macros[macro_name]
    except (AttributeError, KeyError):
        raise template.TemplateSyntaxError(
            "Macro '{0}' is not defined".format(macro_name))
 
    fe_kwargs = {}
    fe_args = []
 
    for val in values:
        if "=" in val:
            # kwarg
            name, value = val.split("=")
            fe_kwargs[name] = FilterExpression(value, parser)
        else:  # arg
            # no validation, go for it ...
            fe_args.append(FilterExpression(val, parser))
 
    macro.parser = parser
    return UseMacroNode(macro, fe_args, fe_kwargs)


class MacroBlockNode(template.Node):
    """ Template node object for the extended
    syntax macro useage.
    """
    def __init__(self, macro, nodelist, args, kwargs):
        self.macro = macro
        self.nodelist = nodelist
        self.args = args
        self.kwargs = kwargs

    def render(self, context):
        # take the macro_block's args, and sub them
        # into the context for macro's args.
        for i, arg in enumerate(self.macro.args):
            try:
                context[arg] = self.args[i].nodelist.render(context)
            except IndexError:
                # have missing args fail silently as usual
                context[arg] = ""

        # take macro_block's kwargs, and sub them
        # into the context for macro's kwargs.
        for name, default in self.macro.kwargs.iteritems():
            try:
                # add the rendered contents of the tag to the context
                context[name] = self.kwargs[name].nodelist.render(context)
            except KeyError:
                context[name] = FilterExpression(default,
                    self.macro.parser).resolve(context)

        return self.macro.nodelist.render(context)


@register.tag(name="macro_block")
def do_macro_block(parser, token):
    """ Function taking parsed template tag
    to a MacroBlockNode.
    """
    try:
        tag_name, macro = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError(
            "{0} tag requires exactly one argument,".format(
                tag_name) + " a macro's name")
    ## need to add some extra validation here.
    try:
        macro = parser._macros[macro]
    except (AttributeError, KeyError):
        raise template.TemplateSyntaxError(
            "Macro '{0}' is not defined".format(macro))
    # get the arg and kwarg nodes from the nodelist
    nodelist = parser.parse(('endmacro_block', ))
    parser.delete_first_token()
    args = nodelist.get_nodes_by_type(MacroArgNode)
    kwargs = dict((x.keyword, x) for x in
        nodelist.get_nodes_by_type(MacroKwargNode))
    macro.parser = parser
    return MacroBlockNode(macro, nodelist, args, kwargs)


class MacroArgNode(template.Node):
    """ Template node object for defining a
    positional argument to a MacroBlockNode.
    """
    def __init__(self, nodelist):
        # save the tag's contents
        self.nodelist = nodelist
    def render(self, context):
        # macro_arg tags output nothing.
        return ''



@register.tag(name="macro_arg")
def do_macro_arg(parser, token):
    """ Function taking a parsed template tag
    to a MacroArgNode.
    """
    # macro_arg takes no arguments, so we don't
    # need to split the token/do validation.
    nodelist = parser.parse(('endmacro_arg',))
    parser.delete_first_token()
    # simply save the contents to a MacroArgNode.
    return MacroArgNode(nodelist)


class MacroKwargNode(template.Node):
    """ Template node object for defining a
    keyword argument to a MacroBlockNode.
    """
    def __init__(self, keyword, nodelist):
        # save keyword so we know where to
        # substitute it later.
        self.keyword = keyword
        # save the tag's contents
        self.nodelist = nodelist

    def render(self, context):
        # macro_kwarg tags output nothing.
        return ''


@register.tag(name="macro_kwarg")
def do_macro_kwarg(parser, token):
    """ Function taking a parsed template tag
    to a MacroKwargNode.
    """
    try:
        tag_name, keyword = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError(
            "{0} tag requires exactly one argument, a keyword".format(
            token.contents.split()[0]))
    # add some validation of the keyword argument here.
    nodelist = parser.parse(('endmacro_kwarg', ))
    parser.delete_first_token()
    return MacroKwargNode(keyword, nodelist)
