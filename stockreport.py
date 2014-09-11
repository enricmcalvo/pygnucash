#!/usr/bin/env python
import codecs
import gnucash
import math
import sys

out = codecs.getwriter('UTF-8')(sys.stdout)
if len(sys.argv) == 1:
	sys.stderr.write("Invocation: %s gnucash_filename\n" % sys.argv[0])
	sys.exit(1)
data = gnucash.read_file(sys.argv[1])

def full_acc_name(acc, maxdepth=1000):
	if acc.parent is None or maxdepth == 0:
		return ""
	result = full_acc_name(acc.parent, maxdepth-1)
	result += ":"+acc.name
	return result

def analyze_transactions(acc):
	sum_shares    = 0
	sum_invest    = 0.0
	sum_costs     = 0.0
	sum_fees      = 0.0
	sum_div_value = 0.0
	sum_div_fees  = 0.0
	sum_div       = 0.0
	first_in      = None
	last_sell     = None

	splits = sorted(acc.splits, key = lambda x: x.transaction.post_date)

	for split in splits:
		trans = split.transaction
		date = trans.post_date.strftime("%d.%m.%Y")
		curr = trans.currency

		shares = split.quantity
		# quantity == 0 it is a dividend marker
		if shares == 0:
			value = 0.0
			fees = 0.0
			dividends = 0.0
			for ssplit in trans.splits:
				if ssplit is split:
					continue
				acctype = ssplit.account.type
				if acctype == "EXPENSE":
					fees += abs(ssplit.value)
				elif acctype == "BANK":
					value += abs(ssplit.value)
				elif acctype == "INCOME":
					dividends += abs(ssplit.value)
				else:
					out.write("UNKNOWN TYPE: %s (acc %s)\n" % (acctype, acc))
					out.write("\t%s %-30s   value %.2f quantity %.2f\n" %
							  (date, trans.description, ssplit.value, ssplit.quantity))
					assert False
			sum_div_value += value
			sum_div_fees  += fees
			sum_div       += dividends
			out.write("\t%s DIV   %7.2f %s fees %7.2f\n" % (date, value, curr, fees))
			continue

		# it is a buy or sell if we are here
		is_buy = split.quantity > 0

		if first_in is None:
			assert is_buy
			first_in = trans.post_date

		# Classify remaining splits into taxes+fees and real costs
		fees  =0.0
		costs =0.0
		atype = "BUY " if is_buy else "SELL"
		for ssplit in trans.splits:
			if ssplit is split or ssplit.value == 0:
				continue
			acctype = ssplit.account.type
			if acctype == "EXPENSE":
				fees += abs(ssplit.value)
			elif acctype == "BANK" or acctype == "ASSET":
				costs += -ssplit.value
			elif acctype == "STOCK" or acctype == "MUTUAL":
				# moved to different depot? or a stock split?
				if ssplit.account == acc:
					# share split
					atype = "SPLT"
					shares += ssplit.quantity
				else:
					# moved to/from different depot, handle like a SELL
					assert costs == 0
					atype = "MIN " if is_buy else "MOUT"
					costs += -ssplit.value
			else:
				out.write("UNKNOWN TYPE: %s (acc %s)\n" % (acctype, acc))
				out.write("\t%s %-30s   value %.2f quantity %.2f\n" %
						  (date, trans.description, ssplit.value, ssplit.quantity))
				assert False

		quantity = abs(split.quantity)
		out.write("\t%s %s %7s shares costs %9.2f %s fees %7.2f\n" % (
		          date, atype, quantity, abs(costs), curr, fees))
		sum_costs  += costs
		sum_fees   += fees
		sum_shares += split.quantity
		if sum_shares == 0:
			last_sell = trans.post_date
		else:
			last_sell = None
		if is_buy:
			sum_invest += costs
	assert abs(sum_div_value+sum_div_fees - sum_div) < .0001
	return (sum_costs, sum_invest, sum_fees, sum_shares, sum_div_value, sum_div_fees, first_in, last_sell)

def get_latest_share_value(acc, shares):
	commodity = acc.commodity
	prices = commodity.prices
	if len(prices) == 0:
		return float('NaN')
	last_price = prices[-1]
	value = shares * last_price.value
	return (value, last_price.date)

# Report
gdiv_value       = 0.0
gdiv_fees        = 0.0
grealized_gain   = 0.0
gunrealized_gain = 0.0
gfees            = 0.0
for acc in data.accounts.values():
	if acc.type != "STOCK" and acc.type != "MUTUAL":
		#out.write("IGNORE %s: %-40s\n" % (acc.type, full_acc_name(acc, 3)))
		continue
	name = full_acc_name(acc, 3)
	out.write("%-40s\n" % (name,))

	costs, invest, fees, shares, div_value, div_fees, first_in, last_sell = analyze_transactions(acc)
	gfees      += fees
	gdiv_value += div_value
	gdiv_fees  += div_fees
	out.write("  => %5.0f shares, %9.2f costs %5.2f dividends %8.2f fees\n" % (shares, costs, div_value, fees + div_fees))
	if shares == 0:
		value, value_date = (0.0, last_sell)
		grealized_gain += -costs
	else:
		value, value_date = get_latest_share_value(acc, shares)
		date = value_date.strftime("%d.%m.%Y")
		out.write("  => share value %11.2f [on %s]\n" % (value, date))
		gunrealized_gain += -costs + value

	# Try to compute win in percentage
	from_date = first_in.strftime("%m/%Y")
	to_date = value_date.strftime("%m/%Y")
	delta = value_date - first_in
	days = delta.days
	win = -costs + value + div_value
	win_ratio = win / invest
	win_per_day = 1.0 if days == 0 else math.pow(1.0+win_ratio, 1.0/float(days))
	win_per_year = math.pow(win_per_day, 365.)
	out.write("  => %2.2f%% gain p.a. (from %s to %s, invested %s)\n" % ((win_per_year-1.0)*100., from_date, to_date, invest))
out.write("-----------\n")
out.write("%9.2f fees\n" % (gdiv_fees+gfees,)) 
out.write("%9.2f EUR gain realized\n" % (grealized_gain,))
out.write("%9.2f EUR gain unrealized\n" % (gunrealized_gain,))
out.write("%9.2f EUR dividends\n" % (gdiv_value,))
out.write("----\n")
out.write("%9.2f EUR complete gain\n" % (grealized_gain+gunrealized_gain+gdiv_value))