import { englishNumber, hindiNumber, rupeesInWords } from "./voice";

test("amounts read in words", () => {
  expect(hindiNumber(40000)).toBe("चालीस हज़ार");
  expect(hindiNumber(125050)).toBe("एक लाख पच्चीस हज़ार पचास");
  expect(englishNumber(4000)).toBe("four thousand");
  expect(englishNumber(250075)).toBe("two lakh fifty thousand seventy-five");
  expect(rupeesInWords(400000, "hi")).toBe("चार हज़ार रुपये");
});
