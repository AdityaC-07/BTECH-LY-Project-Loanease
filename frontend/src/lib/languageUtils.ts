/**
 * Language detection using franc-min library (via CDN).
 * franc-min provides lightweight language detection without dependencies.
 */

export interface DetectionResult {
  detected: boolean;
  language: "en" | "hi" | "unknown";
  confidence: number;
}

/**
 * Detect language from text using franc-min.
 * Falls back to English if detection fails or isn't available.
 */
export const detectLanguage = async (
  text: string
): Promise<DetectionResult> => {
  if (!text || text.trim().length < 3) {
    return {
      detected: false,
      language: "unknown",
      confidence: 0,
    };
  }

  try {
    // Check if franc is available globally (loaded via CDN)
    // @ts-expect-error - franc-min loaded via CDN
    if (typeof franc !== "undefined") {
      // @ts-expect-error - franc global from CDN
      const result = franc(text);

      // franc returns language code, e.g., "eng", "hin"
      if (result === "eng" || result === "en") {
        return { detected: true, language: "en", confidence: 0.9 };
      }
      if (result === "hin" || result === "hi") {
        return { detected: true, language: "hi", confidence: 0.9 };
      }
    }

    // Fallback: simple heuristic detection
    // Check for Hindi Unicode ranges
    const hindiRegex = /[\u0900-\u097F]/g;
    const hindiMatches = text.match(hindiRegex);

    if (hindiMatches && hindiMatches.length / text.length > 0.3) {
      return { detected: true, language: "hi", confidence: 0.7 };
    }

    // Default to English
    return {
      detected: true,
      language: "en",
      confidence: 0.5,
    };
  } catch (error) {
    console.error("Language detection error:", error);
    return {
      detected: false,
      language: "unknown",
      confidence: 0,
    };
  }
};

/**
 * Format number in Indian style (e.g., 5,00,000 instead of 500,000)
 */
export const formatIndianNumber = (num: number): string => {
  if (num === null || num === undefined || isNaN(num)) {
    return "0";
  }
  
  // Handle negative numbers
  const isNegative = num < 0;
  const absNum = Math.abs(num);
  
  // Handle decimal numbers
  const parts = absNum.toFixed(2).split(".");
  const integerPart = parts[0].replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  
  // Remove trailing .00 if present
  const formatted = parts.length > 1 && parts[1] === "00" 
    ? integerPart 
    : `${integerPart}.${parts[1]}`;
  
  return isNegative ? `-₹${formatted}` : formatted;
};

/**
 * Format currency in Indian style with rupee symbol
 */
export const formatIndianCurrency = (amount: number): string => {
  if (amount === null || amount === undefined || isNaN(amount)) {
    return "₹0";
  }
  return `₹${formatIndianNumber(Math.floor(Math.abs(amount)))}`;
};

/**
 * Format EMI with proper currency styling
 */
export const formatEMI = (amount: number, language: "en" | "hi"): string => {
  const currency = formatIndianCurrency(amount);
  const perMonth = language === "en" ? "per month" : "प्रति माह";
  return `${currency} ${perMonth}`;
};

/**
 * Map Hindi risk tier labels
 */
export const getRiskTierLabel = (
  tier: string,
  language: "en" | "hi"
): string => {
  const tierLower = tier.toLowerCase();

  if (tierLower.includes("low")) {
    return language === "en" ? "Low Risk" : "कम जोखिम";
  }
  if (tierLower.includes("medium")) {
    return language === "en" ? "Medium Risk" : "मध्यम जोखिम";
  }
  if (tierLower.includes("high")) {
    return language === "en" ? "High Risk" : "उच्च जोखिम";
  }

  return tier;
};
