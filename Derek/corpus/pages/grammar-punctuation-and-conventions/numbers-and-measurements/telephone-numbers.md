Write telephone numbers so people can read and use them easily. There are rules for grouping the numbers, using spacing and creating links.


Use ‘chunks’ of digits to help people read telephone numbers

Break telephone numbers into shorter blocks of digits or ‘chunks’.

Telephone numbers are easier to read when their digits are chunked, rather than written in one large group.

Australian telephone numbers in general use have no more than 10 digits:

- Landlines – 2 digits for the area code followed by 8 digits for the rest of the telephone number.
- Mobiles – 10 digits (there is no area code).

There are also categories of telephone numbers that don’t have 10 digits – for example, ‘13’ numbers have 6 digits.

### Example

- 02 5550 4321 [A landline number in NSW or the ACT]
- 0491 570 159 [An Australian mobile number]
- 1300 975 707 [An Australia-wide local-rate number]
- 13 00 00 [An alternative Australia-wide local-rate number]
- 1800 160 401 [An Australia-wide freephone number]
- +61 2 5550 4321 [An Australian landline number in international format]
- +61 491 570 159 [An Australian mobile number in international format]

Put a non-breaking space between the chunks of digits

Use a non-breaking space between chunks of digits in a telephone number. A non-breaking space means that line breaks won’t split up the number. The telephone number will stay together on one line.

You can insert a non-breaking space using the Unicode character U+00A0.

In HTML, use the entity to insert a non-breaking space. You can also use the keyboard shortcut Ctrl+Shift+Spacebar in Word.

### Print considerations

Use a narrow no-break space between chunks of digits in a telephone number.

The narrow no-break space ensures that the:

- telephone number stays together on one line
- spacing between digits doesn’t change when text is justified.

You can insert a narrow no-break space using the Unicode character U+202F.

Write telephone numbers in the national or international format

Write telephone numbers in a format appropriate for the location of the users.

### National format for telephone numbers

Use Australia’s national format when writing Australian telephone numbers for content that will be used within Australia.

For landline telephone numbers, write the 2-digit area code followed by a non-breaking space. Then write the rest of the number in 2 chunks of 4 digits.

Write mobile telephone numbers in 1 chunk of 4 digits and then 2 chunks of 3 digits.

#### Example

- 02 5550 4321 [Telephone]
- 0491 570 159 [Mobile]

### International format for telephone numbers

Use international format for content that will be used outside Australia.

The international format uses a plus symbol ’+’ to represent the international prefix, followed by a country code (‘61’ for Australia).

For landline numbers:

- start with a plus symbol ‘+’ and add the country code (‘61’ for Australia)
- add the area code without the ‘0’
- write the telephone number in 2 chunks of 4 digits.

#### Example

- +61 3 7010 4321 [Landline]

For mobile numbers:

- start with a plus symbol ‘+’ and add the country code (‘61’ for Australia)
- omit the first ‘0’
- write the telephone number in 3 chunks of 3 digits.

#### Example

+61 491 578 888 [Mobile]

Always write foreign telephone numbers in the international format.

#### Example

- +1 212 555 0188 [US landline]
- +44 20 7946 0990 [UK landline]

Make telephone numbers accessible through ‘click-to-call’ functionality

‘Click-to-call’ allows users to call a telephone number by selecting (clicking) the number shown in content. When the user selects the number, the user’s mobile phone, other mobile device or personal computer (if it has a supporting application) calls the number.

Click-to-call makes telephone numbers more accessible because users don’t need to copy the number manually. Click-to-call also works with screen readers.

Devices sometimes recognise when a number in content is a telephone number and automatically treat the number as a click-to-call link. This is not always the case, so use HTML code to support this functionality. Seek specialist advice if you’re unsure of how to do this.

### Using HTML for click-to-call

Use ‘tel:[telephone number]’ as the URL. Remove spaces between the numbers.

Remember that all webpages can be accessed internationally. Include the international dialling prefix if appropriate.

#### Example

[02 5550 5722](tel:0255500000)[HTML: <a href="tel:0255505722">02 5550 5722</a>][1300 975 7007](tel:13009757007)[HTML: <a href="tel:13009757007">1300 975 7007</a>][13 83 87](tel:138387)[HTML: <a href="tel:138387">13 83 87</a>][1800 160 401](tel:1800160401)[HTML: <a href="tel:1800160401">1800 160 401</a>][+61 2 7010 0000](tel:+61270100000)[HTML: <a href="tel:+61270100000">+61 2 7010 0000</a>][+61 491 570 156](tel:+61491570156)[HTML: <a href="tel:+61491570156">+61 491 570 156</a>]

Don't use ‘phone words’

Always display the telephone number as digits. Don’t use ‘phone words’. Use the relevant 13 or 1300 number instead.

Some organisations use phone words to advertise their telephone number as a digit-word combination. Don’t do this, because some people find it hard to convert letters to numbers.

### Write this

13 83 87

### Not this

13 VETS


Release notes

The digital edition expands on information in the sixth edition. It includes examples and has more advice about spaces in telephone numbers.

The sixth edition guidance mentions non-breaking and thin spaces and includes spacing allowances for handwritten telephone numbers on forms.

The Content Guide had information about the format of telephone numbers and how to include a clickable link on webpages.

About this page

### References

ACMA (Australian Communications and Media Authority) (2022) [ Buy a custom number](https://www.acma.gov.au/buy-custom-number), ACMA website, accessed 14 January 2022.

ACMA (2022) [ Choose your phone number](https://www.acma.gov.au/choose-your-phone-number), ACMA website, accessed 4 June 2020.

International Telecommunication Union (ITU) (2001) [‘Recommendation ITU-T E123 (02/2001): notation for national and international telephone numbers, e-mail addresses and web addresses’](https://www.itu.int/rec/T-REC-E.123-200102-I/en), *Standardization (ITU-T) recommendations*, ITU website, accessed 2 February 2022.

LePage P (2019) *Click to call*, Web Fundamentals website, accessed 10 February 2022.

Moran K (2016) [ How chunking helps content processing](https://www.nngroup.com/articles/chunking/), Nielsen Norman Group website, accessed 21 January 2022.

North American Numbering Plan Administrator (NANPA) (n.d.) [‘555 line numbers’](https://www.nationalnanpa.com/number_resource_info/555_numbers.html), *Numbering resources*, NANPA website, accessed 21 January 2022.

Ofcom (The Office of Communications) (2004) [ Telephone numbers for use in TV and radio drama programmes](https://www.ofcom.org.uk/phones-telecoms-and-internet/information-for-industry/numbering/numbers-for-drama), Ofcom website, accessed 21 January 2022.

The Unicode Consortium (2022) ‘General punctuation’, [ Unicode 15.0 character code charts](https://www.unicode.org/charts/), Unicode website, accessed 3 November 2022.

The Unicode Consortium (2022) ‘Latin-1 punctuation’, [ Unicode 15.0 character code charts](https://www.unicode.org/charts/), Unicode website, accessed 3 November 2022.

University of Chicago (2017) *Chicago manual of style*, 17th edn, University of Chicago Press, Chicago.

WebAIM (n.d.) [ Links and hypertext](https://webaim.org/techniques/hypertext/), WebAIM website, accessed 9 February 2022.

### Last updated

This page was updated Wednesday 19 February 2025.