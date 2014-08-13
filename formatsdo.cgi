#!/usr/bin/perl

use strict;
use CGI;
use Date::Format;
use Time::HiRes qw( gettimeofday );
use XML::Parser;

use constant {
    ENTITY_NAME => 0,
    ENTITY_ATTRS => 1,
    NODE_ENTITY => 0,
    NODE_CHILDREN => 1,
};

##################
# global variables
##################
our $root_tag;
our $root_tag_found = 0;
our $root_tag_level = 0;
our $xml_tree_level = 1;
our %node_map = ();
our @node_list = ();
our $current_entity_ref;
our ($current_attr_name, $current_attr_val, $current_attr_suffix);
our $current_node_ref;


# initialize CGI and parser
my $q = CGI->new;
my $parser = XML::Parser->new(Handlers => {Start => \&handle_start, Char => \&handle_char, End => \&handle_end});


print $q->header();

print $q->start_html(-title => 'Pricing SDO Formatter',
                     -style => {'src' => '/styles/sdo-formatter.css'},
                     -script => {-language => 'javascript', -src => '/src/sdo-formatter.js'});

### MAIN PAGE LOGIC ###
if ( !$q->param() ) { # if no parameters, then print the form
    &print_form();
}
else {
    print "<div style=\"margin-left: 5%; margin-right: 5%;\">\n";
    print $q->h2("Pricing SDO Formatter") . "\n";
    print "<div class=\"console\">\n";
    print $q->p($q->u({-onClick => "toggle_visibility('debug');"}, 'Debug Console')) . "\n";
    print "<div id=\"debug\" class=\"debug\">\n";

    $root_tag = $q->param('root_tag'); # deprecated
    print "Received root element '$root_tag'" . $q->br . "\n";
    my $payload = $q->param('sdo');
    #print $q->div('The request payload is:', $q->blockquote($q->pre($q->escapeHTML($payload))));

    # parse SDO
    $parser->parse($payload);

    #foreach my $node (@node_list) {
    #    print &generate_hash(${$node}[NODE_ENTITY]) . $q->br . "\n";
    #}
    print "There are <b>" . scalar(keys %node_map) . "</b> nodes in the hash and <b>" . scalar(@node_list) . "</b> nodes in the array." . $q->br . "\n";

    &construct_relationships();

    my @root_node = @{$node_map{$root_tag}};
    print "The root has <b>" . scalar(@{$root_node[NODE_CHILDREN]}) . "</b> children." . $q->br . "\n";

    print "</div>\n";
    print "</div>\n";
    print "<br />\n<br />\n";

    #################
    # print results
    #################

    print "<div class=\"sdotree\">\n"; 
    print $q->h3("Here is your SDO!") . "\n";
    print "<p>Click an entity name to hide or show its details.</p>\n";
    print "<p><span class=\"rollup\">Green entities</span> represent <u>roll-ups</u> (e.g., roll-up charge, aggregate charge component). <span class=\"errormessage\">Red entities</span> represent pricing <u>error messages</u>.<br />\n";
    ### iterate down the node tree and print entities
    &traverse_tree($node_map{$root_tag}, 0);
    print "</div>\n";

    print $q->p($q->a({href => $q->url(-relative => 1)}, 'Do another'));
    print "</div>\n";
}

print $q->end_html;







##############################################################################
# render HTML to display the initial form
##############################################################################
sub print_form {
    print "<div style=\"margin-left: 5%; margin-right: 5%;\">\n";
    print $q->h2("Pricing SDO Formatter") . "\n";
    print $q->p("This will try to format the raw XML output from the Fusion Pricing service into something more human-readable, ",
        "establishing known parent-child relationships between entities like <tt>Header</tt>, <tt>Line</tt>, <tt>Charge</tt>, ",
        "<tt>ChargeComponent</tt>, and <tt>ChargeInput</tt>. <i>NOTE: This is only tested on Firefox.</i>") . "\n";
    print "<div class=\"formbox\">\n";
    print $q->start_form . "\n";
    print "<p>\n";
    print "Paste the price request <b>SDO payload</b> below:\n";
    print $q->textarea(-name => 'sdo',
                       -rows => 24,
                       -columns => 80,
                       -class => 'xmltextinput') . "\n";
    print "</p>\n";
    print "<p>\n";
    print "<i>BETA</i>: The script will try to detect the root element." . $q->br . "\n";
    print "<strike>Specify the <b>root element name</b> without namespace (typically 'result' or 'PriceRequestInternalType'):</strike>" . $q->br . "\n";
    print $q->textfield(-name => 'root_tag',
                        -value => 'result',
                        -size => 60,
                        -disabled => 1) . $q->br . "\n";
    print "</p>\n";
    print $q->submit(-name => 'submit_form',
                     -value => 'Submit') . "\n";
    print $q->end_form . "\n";
    print "</div>\n";
    print "<p><em>Last modified " . time2str('%a %h %d, %Y', (stat $0)[9]) . "</em></p>\n";
    print "</div>\n";
}




##############################################################################
# XML start tag handler
##############################################################################
sub handle_start {
    my ($expat, $element, %attrs) = @_;

    $xml_tree_level++;

    # ignore namespace
    $element =~ /^(\w+:)?(\S*)$/;
    my $tag = $2;

    # start processing only if the root tag is reached
    #if ( !$root_tag_found and $tag eq $root_tag ) {
    if ( !$root_tag_found ) {
        foreach ( values %attrs ) {
            if ( /^http\:\/\/xmlns\.oracle\.com\/apps\/scm\/pricing\/priceExecution\/pricingProcesses\/((priceRequestService\/)|(PriceRequestInternal))$/ ) {
                print "<span style=\"color: grey;\">handle_start():</span> found root element $tag" . $q->br . "\n";
                $root_tag_found = 1;
                $root_tag_level = $xml_tree_level;
                $root_tag = $tag;
                last;
            }
        }
    }
    return if !$root_tag_found;

    my $diff = $xml_tree_level - $root_tag_level;
    if ( $diff==0 ) { # root tag
        # create empty node to serve as placeholder for the root
        $node_map{$root_tag} = [[$root_tag, {}], []];
    }

    elsif ( $diff==1 ) { # context entity
        $current_entity_ref = [$tag, {}];
        print "<span style=\"color: grey;\">handle_start():</span> entity " . $tag . $q->br . "\n";
    }
    elsif ( $diff==2 ) { # context entity attribute
        # prepare a new attribute record
        $current_attr_name = $tag;
        $current_attr_val = '';
        $current_attr_suffix = '';

        print "<span style=\"color: grey;\">handle_start():</span> attribute " . $tag . $q->br . "\n";

        # the only XML attributes we're interested in are unitCode and currencyCode
        if ( $attrs{'unitCode'} ) {
            $current_attr_suffix = "$attrs{'unitCode'}";
            print "<span style=\"color: grey;\">handle_start():</span> unitCode = " . $current_attr_suffix . $q->br . "\n";
        }
        elsif ( $attrs{'currencyCode'} ) {
            $current_attr_suffix = $attrs{'currencyCode'};
            print "<span style=\"color: grey;\">handle_start():</span> currencyCode = " . $current_attr_suffix . $q->br . "\n";
        }
    }

}

##############################################################################
# XML char handler
##############################################################################
sub handle_char {
    my ($expat, $text) = @_;
    chomp $text;

    return if (!$root_tag_found or $text eq '');

    my $diff = $xml_tree_level - $root_tag_level;
    if ($diff == 2) { # context entity attribute
        $current_attr_val = $text;
        $current_attr_val .= " $current_attr_suffix" if $current_attr_suffix ne '';
    }
}


##############################################################################
# XML end tag handler
##############################################################################
sub handle_end {
    return if !$root_tag_found;

    my $diff = $xml_tree_level - $root_tag_level;
    if ($diff == 2 and $current_attr_val ne '') {
        $current_entity_ref->[ENTITY_ATTRS]->{$current_attr_name} = $current_attr_val;
        #print "<span style=\"color: grey;\">handle_end():</span> attribute " . $current_attr_name . " = " . $current_attr_val . $q->br . "\n";
    }
    elsif ($diff == 1) { # construct node once we have entity
        $current_node_ref = [$current_entity_ref, []];

        push @node_list, $current_node_ref;
        $node_map{&generate_hash($current_entity_ref)} = $current_node_ref;
    }

    $xml_tree_level--;
    $root_tag_found = 0 if $xml_tree_level<$root_tag_level;
}



##############################################################################
# Generate a hash of an entity to insert into the node map
#
# An entity is hashed to the string <entity name>+'_'+<unique ID>.
# The unique ID is either the entity's primary attribute (<entity name>+'Id'),
# or, if that attribute does not exist, the current millisecond epoch time.
#
# Exceptions to the rule must be coded separately.
#
# NOTE: Root tags do not have unique IDs.
##############################################################################
sub generate_hash {
    my $entity_ref = shift;

    my $hash_val;
    my $entity_name = $entity_ref->[ENTITY_NAME];

    if ($entity_name eq $root_tag) {
        $hash_val = $root_tag;
    }
    elsif ($entity_name eq "SalesOrderTotal") {
        $hash_val = $entity_name . "_" . $entity_ref->[ENTITY_ATTRS]->{"TotalId"};
    }
    else {
        my $guess = $entity_ref->[ENTITY_ATTRS]->{$entity_name . "Id"};
        if ( $guess ne '' ) {
            $hash_val = $entity_name . "_" . $guess;
        }
        else {
            my ($seconds, $micros) = gettimeofday();
            $hash_val = $entity_name . "_" . (100000*$seconds + $micros);
        }
    }

    return $hash_val;
}




##############################################################################
# Iterate through all the nodes and construct known parent-child
# relationships
##############################################################################
sub construct_relationships {
    # iterate through nodes
    foreach my $node_ref (@node_list) {
        my $entity_ref = ${$node_ref}[NODE_ENTITY];
        my $name = ${$entity_ref}[ENTITY_NAME];
        my %attrs = %{${$entity_ref}[ENTITY_ATTRS]};

        my $parent_hash_str;
        my @parent_node;
        if ($name eq "Line" and $attrs{"HeaderId"}) {
            # attach line to header
            $parent_hash_str = "Header_" . $attrs{"HeaderId"};
        }
        elsif ($name eq "Charge" and $attrs{"ParentEntityCode"} eq "LINE" and $attrs{"ParentEntityId"} ne '') {
            # attach charge to line
            $parent_hash_str = "Line_" . $attrs{"ParentEntityId"};
        }
        elsif ($name eq "ChargeCandidate" and $attrs{"ParentEntityCode"} eq "LINE" and $attrs{"ParentEntityId"} ne '') {
            # attach charge candidate to line
            $parent_hash_str = "Line_" . $attrs{"ParentEntityId"};
        }
        elsif ($name eq "ChargeComponent" and $attrs{"ChargeId"} ne '') {
            # attach charge component to charge
            $parent_hash_str = "Charge_" . $attrs{"ChargeId"};
        }
        elsif ($name eq "ChargeInput" and $attrs{"ChargeParentEntityCode"} eq "LINE" and $attrs{"ChargeParentEntityId"} ne '') {
            # attach charge input to line
            $parent_hash_str = "Line_" . $attrs{"ChargeParentEntityId"};
        }
        elsif ($name eq "PricingMessage" and $attrs{"ParentEntityCode"} eq "LINE" and $attrs{"ParentEntityId"} ne '') {
            $parent_hash_str = "Line_" . $attrs{"ParentEntityId"};
        }
        elsif ($name eq "PricingMessage" and $attrs{"ParentEntityCode"} eq "HEADER" and $attrs{"ParentEntityId"} ne '') {
            $parent_hash_str = "Header_" . $attrs{"ParentEntityId"};
        }
        elsif ($name eq "SalesOrderTotalComponent" and $attrs{"TotalId"}) {
            # attach sales order total component to sales order total
            $parent_hash_str = "SalesOrderTotal_" . $attrs{"TotalId"};
        }
        elsif ($name eq "TaxLineDetail" and $attrs{"ChargeComponentId"}) {
            # attach tax line detail to charge component
            $parent_hash_str = "ChargeComponent_" . $attrs{"ChargeComponentId"};
        }
        else {
            # attach to the root tag
            $parent_hash_str = $root_tag;
        }
        @parent_node = @{$node_map{$parent_hash_str}};
        push @{$parent_node[NODE_CHILDREN]}, $node_ref;
        print "<span style=\"color: grey;\">construct_relationships():</span> attaching " . &generate_hash($entity_ref) . " to " . &generate_hash($parent_node[NODE_ENTITY]) . $q->br . "\n";
    }
}




sub print_entity {
    my ($entity_ref, $indent_level) = @_;
    my @entity = @{$entity_ref};
    my $hash_str = &generate_hash($entity_ref);
    my $display_str = $entity[ENTITY_NAME];
    my %attrs = %{$entity[ENTITY_ATTRS]};

    print $q->br . "\n";
    print "<div class=\"spacer\">&nbsp;</div>" x ($indent_level) . "\n";
    # roll-up entities have a different color
    if ( $attrs{"RollupFlag"} eq "true" ) {
        print "<div class=\"entity rollup\">\n";
    }
    # so do error pricing messages
    elsif ($display_str eq "PricingMessage" && $attrs{"MessageTypeCode"} eq "ERROR") {
        print "<div class=\"entity errormessage\">\n";
    }
    else {
        print "<div class=\"entity\">\n";
    }
    print "<div class=\"entityname\" onClick=\"toggle_visibility('$hash_str')\">$display_str</div>\n";
    print "<div id=\"$hash_str\" style=\"display: none;\">\n";
    print $q->hr . "\n";

    foreach my $attr (sort keys %attrs) {
        my $attrname = $attr;
        my $attrval = $attrs{$attr};

        # expand a camel-case attribute name with spaces
        $attrname =~ s/([a-z])([A-Z])/$1 $2/g;
        # special handling for capitalized acronyms in camel-case (e.g., "UOM")
        $attrname =~ s/(\w)([A-Z][a-z])/$1 $2/g;
        # turn "Id" into "ID"
        $attrname =~ s/(\s)Id/$1ID/;

        # custom visual transformations for attribute values
        # Boolean true
        if ( $attrval eq "true" or $attrval eq 'Y' ) {
            $attrval = "<span style=\"color: #00CC33;\">&#x2714;</span>";
        }
        # Boolean false
        elsif ( $attrval eq "false" or $attrval eq 'N' ) {
            $attrval = "<span style=\"color: red;\">&#x2718;</span>";
        }
        # dates
        elsif ( $attrval =~ /^(\d{4}\-\d{2}\-\d{2})T(\d{2}\:\d{2}\:\d{2})/) {
            $attrval = "$1 @ $2";
        }

        print "$attrname: " . $attrval . $q->br . "\n";
    }
    print "</div>\n";
    print "</div><br />\n";
}




sub traverse_tree {
    my ($root_node_ref, $depth) = @_;
    my $entity_ref = $root_node_ref->[NODE_ENTITY];
    my $children_ref = $root_node_ref->[NODE_CHILDREN];

    if ( $entity_ref->[ENTITY_NAME] ne $root_tag ) {
        &print_entity($entity_ref, $depth++);
    }

    foreach (@{$children_ref}) {
        &traverse_tree($_, $depth);
    }
}
