#! /usr/bin/perl -w

use strict;
use warnings;

# This script was tested on 5.18.0
use 5.18.0;

use POSIX;      # ceil

use lib qw(lib);
use CaseHash;


#----------------------------------------
# parsing
#----------------------------------------

my $integer = qr/(?:\d+)/;
my $number = qr/(?:[+\-]?(?:\d+(?:\.\d*)?|\d*\.\d+)(?:[eE][+\-]?\d+)?)/;
my $thingy = qr/(?:[^\s,;!]+)/;
my $identifier = qr/(?:[a-zA-Z][\w\.]*)/;
my $string = qr/(?:"[^"]*")/;

my $param = qr/(?:$string|$thingy)/;
my $with_arg = qr/\s*:?=\s*($param)/;
my $with_num = qr/\s*:?=\s*($number)/;
my $with_int = qr/\s*:?=\s*($integer)/;


sub parse_element
{
    if ($_[0] =~ /^\s*(?:($identifier)\s*:)?\s*($identifier)\s*(,.*)?;\s*$/) {
        my $name = $1 // '';
        my $type = $2 // '';
        my $def = $3 // '';
        my $attr = new CaseHash();
        while ($def =~ /,\s*($identifier)$with_arg/g) {
            $attr->{$1 // ''} = $2 // '';
        }
        return {'text' => $_[0],
                'name' => $name,
                'type' => $type,
                'def' => $def,
                'attr' => $attr};
    }
    else {
        return {'text' => $_[0]};
    }
}

sub parse_line
{
    my @elements;

    # split comments
    $_[0] =~ '^([^!]*)(!.*)?$';
    my ($code, $comment) = ($1 // '', $2 // '');

    if ($comment ne '') {
        push @elements, {'text' => $comment};
    }

    # parse expressions
    while ($code =~ /[^;]+;/g) {
        push @elements, parse_element($&);
    }

    if (@elements == 0) {
        push @elements, {'text' => ''};
    }

    return @elements;
}

sub parse_stdin
{
    my @elems;
    while (my $line = <STDIN>) {
        chomp($line);
        push @elems, parse_line($line);
    }
    return @elems;
}


#----------------------------------------
# formatting
#----------------------------------------

sub scinum
{
    return sprintf("%.8e", $_[0])
}

sub format_element
{
    my ($elem) = @_;

    if (!defined($elem->{'type'})) {
        return $elem->{'text'} // '';
    }

    my $name = $elem->{'name'} // '';
    my $type = $elem->{'type'};
    my $def = $elem->{'def'} // '';

    while (my ($name, $value) = each($elem->{'attr'})) {
        if (defined($value)) {
            # replace updated values
            if ($def =~ /,\s*$name$with_arg/i) {
                if ($1 ne $value) {
                    $def =~ s/,(\s*)$name$with_arg/,$1$name:=$value/i;
                }
            }
            # insert new values
            else {
                $def .= ", $name:=$value";
            }
        }
        # remove undef'ed fields
        else {
            $def =~ s/,\s*$name$with_arg//i;
        }
    }

    my $text = "$type$def;";
    $text = "$name: $text" if ($name ne '');
    return $text;
}


#----------------------------------------
# element filters
#----------------------------------------

sub filter_default
{
    my ($offset,
        $refer,
        $elem) = @_;
    my $attr = $elem->{'attr'};

    $attr->{'at'} = scinum($offset + $refer*($attr->{'L'} // 0));
    return $elem;
}

sub detect_slicing
{
    my ($elem,
        $slicing) = @_;
    my $attr = $elem->{'attr'};

    # fall through for elements without explicit slice attribute
    $slicing = $attr->{'slice'} // $slicing;
    undef $attr->{slice};
    return undef if (!defined($slicing));

    my $elem_len = $attr->{'L'} // 0;
    return undef if ($elem_len == 0);

    # determine slice number, length
    my ($slice_num,
        $slice_len);
    if ($slicing =~ /^($number)\/m$/) {
        $slice_num = ceil(abs($elem_len * $1));
        $slice_len = $elem_len / $slice_num;
    }
    elsif ($slicing =~ /^($integer)$/) {
        $slice_num = $1;
        $slice_len = $elem_len / $slice_num;
    }
    else {
        die "invalid slicing: $slicing";
    }

    $elem->{'slice_num'} = $slice_num;
    $elem->{'slice_len'} = $slice_len;

    # replace L property
    $attr->{'L'} = scinum($slice_len);
    return $elem;
}

sub typecast_preserve
{
    my ($elem) = @_;
    my $attr = $elem->{'attr'};

    # check for element type
    my $type = lc($elem->{'type'} // '');
    if ($type eq 'sbend') {
        $attr->{'angle'} = '('.$attr->{'angle'}.') / '.$elem->{'slice_num'};
    }
}

# NOTE: typecast_multipole is currently not recommended!
# If you use it, you have to make sure, your slice length will be
# sufficiently small!
# You should use Mad-X' MAKETHIN or not use it at all!
sub typecast_multipole
{
    my ($elem) = @_;
    my $attr = $elem->{'attr'};

    # check for element type
    my $type = lc($elem->{'type'} // '');
    if ($type eq 'sbend') {
        $attr->{knl} = '{(('.$attr->{angle}.')/('.$elem->{slice_num}.'))}';
        undef $attr->{angle};
        undef $attr->{HGAP};
    }
    elsif ($type eq 'quadrupole') {
        $attr->{knl} = '{0, (('.$attr->{k1}.')*('.$attr->{L}.'))}';
        undef $attr->{k1};
    }
    else {
        return;
    }

    # set elem_class to multipole
    $elem->{type} = 'multipole';
    # replace L by LRAD property
    $attr->{lrad} = $attr->{L};
    undef $attr->{L};
}

sub slice_simple
{
    my ($offset,
        $refer,
        $elem) = @_;
    my $attr = $elem->{'attr'};

    my @elems;
    foreach my $slice_idx (0..($elem->{slice_num}-1)) {
        my $slice = {
            'type' => $elem->{'type'},
            'def' => $elem->{'def'},
            'attr' => new CaseHash(%$attr),
        };
        if (defined($elem->{name})) {
            $slice->{name} = $elem->{'name'} . '..' . $slice_idx;
        }
        $slice->{'attr'}{'at'} = scinum($offset + ($slice_idx + $refer)*$elem->{slice_len});
        push @elems, $slice;
    }
    return undef, @elems;
}

sub slice_optics
{
    my ($offset,
        $refer,
        $elem) = @_;
    my $attr = $elem->{'attr'};

    my @elems;
    foreach my $slice_idx (0..($elem->{slice_num}-1)) {
        push @elems, {
            'name' => $elem->{name} . '..' . $slice_idx,
            'type' => $elem->{'name'},
            'attr' => new CaseHash(at => scinum($offset + ($slice_idx + $refer)*$elem->{slice_len})),
        };
    }
    return $elem, @elems;
}

sub slice_optics_short
{
    my ($offset,
        $refer,
        $elem) = @_;
    my $attr = $elem->{'attr'};

    my @elems;
    foreach my $slice_idx (0..($elem->{slice_num}-1)) {
        push @elems, {
            'type' => $elem->{'name'},
            'attr' => new CaseHash(at => scinum($offset + ($slice_idx + $refer)*$elem->{slice_len})),
        };
    }
    return $elem, @elems;
}



sub slice_loops
{
    my ($offset,
        $refer,
        $elem) = @_;
    my $attr = $elem->{'attr'};
    my $len = $attr->{l} // $attr->{lrad};

    return $elem, (
        { 'text' => 'i = 0;' },
        { 'text' => 'while (i < ' . $elem->{slice_num} . ') {' },
        {
            'type' => $elem->{'name'},
            'attr' => new CaseHash(at => "($offset) + (i + $refer) * ($len)"),
        },
        { 'text' => 'i = i + 1;' },
        { 'text' => '}' },
    );
}

#----------------------------------------
# top level post processing
#----------------------------------------

sub make_sequence
{
    my $beg = shift;
    my $end = pop;
    my $attr = $beg->{'attr'};

    # handle REFER
    my %offsets = (
        'entry' => 0,
        'centre' => 0.5,
        'exit' => 1 );
    my $refer = $offsets{lc($attr->{'refer'} // 'centre')};

    # select default slicing
    my $default_slice = $attr->{'slice'} // undef;
    undef $attr->{'slice'};
    # TODO: when to slice: explicit/always/never/{select classes}

    # select typecast routine
    my %typecast = (
        'preserve' => \&typecast_preserve,
        'multipole' => \&typecast_multipole,
    );
    my $typecast = $typecast{lc($attr->{typecast} // 'preserve')};
    undef $attr->{typecast};

    # select optics routine
    my $optics_file = lc($attr->{'optics'} // 'inline');
    if ($optics_file eq 'inline') {
        $optics_file = '';
    }
    elsif ($optics_file !~ s/\s*"(.*)"\s*/$1/) {
        die "invalid optics: $optics_file";
    }
    undef $attr->{'optics'};

    # output method
    my %slice_method = (
        'simple' => \&slice_simple,
        'optics' => \&slice_optics,
        'optics-short' => \&slice_optics_short,
        'loops' => \&slice_loops
    );
    my $slice_method = $slice_method{lc($attr->{'method'} // 'simple')};
    undef $attr->{'method'};

    # iterate through sequence
    my @elems;
    my @optics;
    my $length = 0;
    foreach my $elem (@_) {
        if (defined($elem->{'type'})) {
            my $elem_len = $elem->{'attr'}{'L'} // 0;
            if (detect_slicing($elem, $default_slice)) {
                &$typecast($elem);
                my ($optic,
                    @elem) = &$slice_method($length, $refer, $elem);
                push @optics, $optic if (defined($optic));
                push @elems, @elem;
            }
            else {
                push @elems, filter_default($length, $refer, $elem);
            }

            $length += $elem_len;
        }
        else {
            push @elems, $elem;
        }
    }
    $attr->{'L'} = scinum($length);

    if (@optics) {
        @optics = (
            {text => '! Optics definition for ' . $beg->{name} . ':'},
            @optics,
            {text => ''}
        );

        if ($optics_file) {
            open(my $fh, ">", $optics_file)
                or die "Can not open optics file: $optics_file";

            print $fh join("\n", map { format_element($_) } @optics);
            close($fh);

            @optics = ();
        }
    }

    return @optics,
        {text => '! Sequence definition for ' . $beg->{name} . ':'},
        $beg, @elems, $end;
}

sub make_sequences
{
    my @elems;
    my $N = @_;

    for (my $i = 0; $i < $N; ++$i) {
        my $elem = $_[$i];

        if (lc($elem->{'type'} // '') eq 'sequence') {
            my $j;
            for ($j = $i + 1; $j < $N; ++$j) {
                last if (lc($_[$j]{'type'} // '') eq 'endsequence');
            }
            push @elems, make_sequence(@_[$i..$j]);
            $i = $j;
        }
        else {
            push @elems, $elem;
        }
    }
    return @elems;
}

#----------------------------------------
# main program call
#----------------------------------------

print join("\n", map { format_element($_) } make_sequences(parse_stdin()));

