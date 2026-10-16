"use client";

import React, { useState, useEffect } from "react";
import { Search, X, Loader2 } from "lucide-react";

export interface SearchBarProps {
  onSearch: (query: string) => void;
  isLoading?: boolean;
  placeholder?: string;
}

export function SearchBar({
  onSearch,
  isLoading = false,
  placeholder = "Search by error trace, tool call, or task goal...",
}: SearchBarProps) {
  const [query, setQuery] = useState("");

  // Debounce query updates by 350ms to prevent excessive API invocations
  useEffect(() => {
    const handler = setTimeout(() => {
      onSearch(query);
    }, 350);

    return () => {
      clearTimeout(handler);
    };
  }, [query, onSearch]);

  const handleClear = () => {
    setQuery("");
  };

  return (
    <div className="relative w-full">
      {/* Search Icon */}
      <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-zinc-400">
        <Search className="h-5 w-5" />
      </div>

      {/* Search Input */}
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-12 pr-12 py-3.5 rounded-2xl border border-zinc-800 bg-zinc-950/80 text-zinc-100 placeholder-zinc-500 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 transition-all shadow-inner backdrop-blur-sm"
      />

      {/* Right Icons: Spinner and Clear Button */}
      <div className="absolute inset-y-0 right-0 pr-4 flex items-center gap-2">
        {isLoading && (
          <Loader2 className="h-4 w-4 animate-spin text-emerald-400 shrink-0" />
        )}

        {query.length > 0 && (
          <button
            type="button"
            onClick={handleClear}
            className="p-1 rounded-full text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors focus:outline-none"
            aria-label="Clear search"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
