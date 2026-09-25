/**
 * The same maths as backend/main.py, on the device.
 *
 * This exists for one reason: phone signal inside big stores is bad. The
 * installed app keeps working with no connection at all, and the shopper gets
 * the same number the server would have given.
 *
 * Matching the server exactly is harder than it looks. Python rounds a float by
 * looking at its exact binary value and breaking ties to even; the usual
 * JavaScript shortcut of `Math.round(value * 100) / 100` first multiplies, and
 * that multiplication can land exactly on a half cent that was never there:
 *
 *     $200.22 with 75% off -> 200.22 * 0.25 = 50.05499999999999971...
 *     Python: round(..., 2) = 50.05        (the value is below half a cent)
 *     Math.round(v * 100)   = 5006 -> 50.06 (v * 100 rounded up to exactly 5005.5)
 *
 * So the price would change by a cent depending on signal. `roundHalfEven`
 * below does what Python does: convert to an exact decimal expansion, then
 * round half to even. tools/check_parity.py fuzzes the two implementations
 * against each other (6000+ cases) to keep them honest.
 */

const MAX_FIXED_DIGITS = 100;

/** Round like Python's round(): ties go to the even digit, using the exact value. */
export function roundHalfEven(value, decimals) {
  if (!Number.isFinite(value)) return value;

  // Enough decimals to see the exact expansion of the double without hitting
  // toFixed's own 100-digit ceiling.
  const digits = Math.min(MAX_FIXED_DIGITS, Math.max(decimals + 25, 30));
  const fixed = Math.abs(value).toFixed(digits);
  const [whole, fraction = ""] = fixed.split(".");
  if (fraction.length <= decimals) return value; // nothing to round away

  const kept = fraction.slice(0, decimals);
  const dropped = fraction.slice(decimals);

  let scaled = BigInt(whole + kept);
  const isTie = dropped[0] === "5" && /^0*$/.test(dropped.slice(1));
  const roundUp = isTie ? scaled % 2n === 1n : dropped[0] >= "5";
  if (roundUp) scaled += 1n;

  const rounded = Number(scaled) / 10 ** decimals;
  return value < 0 ? -rounded : rounded;
}

export function calculatePriceLocally(originalPrice, discount1Pct, discount2Pct = 0) {
  const priceAfterFirst = originalPrice * (1 - discount1Pct / 100);
  const finalPrice = discount2Pct
    ? priceAfterFirst * (1 - discount2Pct / 100)
    : priceAfterFirst;
  const saved = originalPrice - finalPrice;

  return {
    original_price: roundHalfEven(originalPrice, 2),
    final_price: roundHalfEven(finalPrice, 2),
    amount_saved: roundHalfEven(saved, 2),
    total_discount_pct: roundHalfEven((saved / originalPrice) * 100, 1),
  };
}
