# Pizza Builder data for R. Base R only (no packages needed).
#
#   source("load_pizza.R")
#   pz <- load_pizza("pizza_results")      # the folder analyse.py wrote (or the unzipped "Download for R" file)
#   str(pz$participants)                   # one row per pizza; see pz$variables for every column
#   people <- pizza_wide(pz)               # one row per participant: own pizza + typical pizza + profile scores
#
# Every table is read with the types and factor levels in variables.csv: integers, doubles, text, and factors whose
# first level is the reference level (e.g. neurotype "Not ND", sauce "tomato"); ordered factors where the levels
# have an order (age_band, diet_class, normality_band, cheese, feel, ...). Missing values are NA. Yes/no columns are
# 0/1 integers. Times are ms, positions are pizza radii (crust edge = 1 = 15 cm, y up). Each column carries its
# description as attr(x, "label") (shown by RStudio's View()); pizza_describe("mirror_score") prints it.

load_pizza <- function(dir = ".") {
  vars <- utils::read.csv(file.path(dir, "variables.csv"), colClasses = "character", na.strings = character(0),
                          encoding = "UTF-8")
  out <- list(variables = vars)
  for (tab in unique(vars$file)) {
    v <- vars[vars$file == tab, ]
    cls <- ifelse(v$type == "integer", "integer", ifelse(v$type == "double", "numeric", "character"))
    names(cls) <- v$column
    d <- utils::read.csv(file.path(dir, paste0(tab, ".csv")), colClasses = cls, na.strings = "NA",
                         check.names = FALSE, encoding = "UTF-8", stringsAsFactors = FALSE)
    for (i in seq_len(nrow(v))) {
      col <- v$column[i]
      if (v$type[i] %in% c("factor", "ordered")) {
        lev <- if (nzchar(v$levels[i])) strsplit(v$levels[i], "|", fixed = TRUE)[[1]] else character(0)
        d[[col]] <- factor(d[[col]], levels = lev, ordered = v$type[i] == "ordered")
      }
      attr(d[[col]], "label") <- v$description[i]
      if (nzchar(v$unit[i])) attr(d[[col]], "unit") <- v$unit[i]
    }
    out[[tab]] <- d
  }
  out
}

# One row per participant: the own pizza's measures, the "typical participant" pizza's measures (if that build was
# used) prefixed typical_, and the profile scores (z_*) and cluster.
pizza_wide <- function(pz) {
  p <- pz$participants
  own <- p[p$build == "pz", , drop = FALSE]
  typ <- p[p$build == "pzt", , drop = FALSE]
  if (nrow(typ)) {
    keep <- setdiff(names(typ), c("pid", "build"))
    names(typ)[match(keep, names(typ))] <- paste0("typical_", keep)
    own <- merge(own, typ[, setdiff(names(typ), "build"), drop = FALSE], by = "pid", all.x = TRUE, sort = FALSE)
  }
  if (!is.null(pz$profiles) && nrow(pz$profiles)) {
    prof <- pz$profiles[, c("pid", grep("^z_", names(pz$profiles), value = TRUE)), drop = FALSE]
    own <- merge(own, prof, by = "pid", all.x = TRUE, sort = FALSE)
  }
  rownames(own) <- NULL
  own
}

# The description, unit and levels of a column (in any table).
pizza_describe <- function(column, pz = NULL, dir = ".") {
  vars <- if (is.null(pz)) utils::read.csv(file.path(dir, "variables.csv"), colClasses = "character", encoding = "UTF-8") else pz$variables
  v <- vars[vars$column == column, c("file", "type", "levels", "unit", "description")]
  if (!nrow(v)) stop("no column called ", column)
  v
}

# Examples (not run):
#   pz <- load_pizza("pizza_results")
#   people <- pizza_wide(pz)
#   table(people$neurotype, people$diet_class)
#   wilcox.test(mirror_score ~ nd_autistic, data = people)
#   # which toppings people include, by neurotype, with a random effect per participant (lme4 package):
#   ing <- merge(pz$ingredients_long[pz$ingredients_long$build == "pz", ], people[, c("pid", "neurotype")], by = "pid")
#   # lme4::glmer(included ~ neurotype * tier + (1 | pid) + (1 | ing), family = binomial, data = ing)
#   # where pieces are placed: one row per piece
#   aggregate(cbind(r, mirror_matched) ~ ing, data = pz$pieces_long, FUN = mean)
