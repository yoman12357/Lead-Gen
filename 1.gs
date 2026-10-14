var LEAD_SORTER_CONFIG = {
  // Change "P" to "B" here only if your actual third source sheet is named B.
  SOURCE_SHEETS: ["A", "S", "B", "H"],

  FINAL_SHEET: "Final List",
  NO_EMAIL_SHEET: "No Emails Leads",
  LESS_FOLLOWERS_SHEET: "Less Followers",
  SUMMARY_SHEET: "Execution Summary",
  PREVIEW_SHEET: "Lead Sorter Preview",

  FOLLOWER_THRESHOLD: 10000,

  // Visible routing/review columns.
  DATE_INDEX: 16, // Q, zero-based
  UPDATED_INDEX: 17, // R
  SOURCE_INDEX: 18, // S
  REMARKS_INDEX: 19, // T
  SUGGESTED_FIX_INDEX: 20, // U

  // Hidden helper columns used by Undo Last Run.
  RUN_ID_INDEX: 21, // V
  PREVIOUS_REMARKS_INDEX: 22, // W
  PREVIOUS_FIX_INDEX: 23, // X

  OUTPUT_COLUMNS: 24, // A:X

  LAST_RUN_ID_PROPERTY: "LEAD_SORTER_LAST_RUN_ID",
  LAST_RUN_STATUS_PROPERTY: "LEAD_SORTER_LAST_RUN_STATUS",
};

/**
 * BUTTON FUNCTION 1: Preview only. Nothing is moved or edited in source sheets.
 *
 * Assign this function to your Preview shape:
 * previewLeadSorter
 */
function previewLeadSorter() {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);

  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var cfg = LEAD_SORTER_CONFIG;
    var today = getTodayKey_(ss);
    var historicalEmails = getHistoricalFinalEmails_(ss, today, cfg);

    var summary = {
      total: 0,
      finalList: 0,
      noEmail: 0,
      lessFollowers: 0,
      staysInSource: 0,
      historicalDuplicates: 0,
    };

    var previewRows = [];

    cfg.SOURCE_SHEETS.forEach(function (sheetName) {
      var sheet = ss.getSheetByName(sheetName);
      if (!sheet || sheet.getLastRow() < 2) return;

      var lastRow = sheet.getLastRow();
      var lastColumn = Math.max(sheet.getLastColumn(), 1);
      var values = sheet.getRange(1, 1, lastRow, lastColumn).getValues();
      var headers = values[0];
      var indexes = getLeadColumnIndexes_(headers);

      for (var i = 1; i < values.length; i++) {
        var row = values[i];
        if (isBlankRow_(row) || isStructuralRow_(row)) continue;

        summary.total++;

        var name = cleanText_(row[0]);
        var email = cleanText_(row[indexes.email]);
        var emailKey = normalizeEmail_(email);
        var instagram = cleanText_(row[indexes.instagram]);
        var tiktok = cleanText_(row[indexes.tiktok]);
        var followerRaw = getFollowerRaw_(row, indexes);
        var followerAssessment = assessFollowers_(
          followerRaw,
          cfg.FOLLOWER_THRESHOLD,
        );

        var action = "";
        var remark = "";
        var suggestedFix = "";

        if (email === "") {
          action = "Move to No Emails Leads";
          remark = "Email is blank.";
          suggestedFix = "Find and add a verified public business email.";
          summary.noEmail++;
        } else if (followerAssessment.routeToLessFollowers) {
          action = "Move to Less Followers";

          if (followerAssessment.reason === "missing") {
            remark = "Follower count is missing or unreadable.";
            suggestedFix =
              "Enter an exact follower count such as 12500 or 12.5k.";
          } else if (followerAssessment.reason === "ambiguous") {
            remark =
              "Follower range crosses the 10K threshold, so qualification cannot be confirmed.";
            suggestedFix =
              "Replace the follower bucket with the exact current follower count.";
          } else {
            remark = "Follower count is below 10,000.";
            suggestedFix =
              "Keep this lead in Less Followers or review it again when the audience grows.";
          }

          summary.lessFollowers++;
        } else if (instagram === "" && tiktok === "") {
          action = "Keep in Source";
          remark = "Instagram and TikTok links are both missing.";
          suggestedFix =
            "Add at least one valid Instagram or TikTok profile link.";
          summary.staysInSource++;
        } else if (emailKey && historicalEmails[emailKey]) {
          action = "Keep/Return to Source: Historical Duplicate";
          remark =
            "This email already exists in Final List from an earlier date.";
          suggestedFix =
            "Review the older lead. Keep this row only if it is a genuinely different contact and update it with a different verified email.";
          summary.historicalDuplicates++;
          summary.staysInSource++;
        } else {
          action = "Move to Final List";
          remark = "Meets the current email, follower and social-link rules.";
          suggestedFix = "No fix required.";
          summary.finalList++;
        }

        previewRows.push([
          sheetName,
          i + 1,
          name,
          email,
          cleanText_(followerRaw),
          instagram,
          tiktok,
          action,
          remark,
          suggestedFix,
        ]);
      }
    });

    writePreviewSheet_(ss, today, summary, previewRows, cfg);

    showMessage_(
      "Lead Sorter Preview",
      [
        "Nothing has been moved.",
        "",
        "Total leads scanned: " + summary.total,
        "Would move to Final List: " + summary.finalList,
        "Would move to No Emails Leads: " + summary.noEmail,
        "Would move to Less Followers: " + summary.lessFollowers,
        "Would remain/return to source: " + summary.staysInSource,
        "Historical duplicates: " + summary.historicalDuplicates,
        "",
        'Detailed results are in the "' + cfg.PREVIEW_SHEET + '" sheet.',
      ].join("\n"),
    );
  } finally {
    lock.releaseLock();
  }
}

/**
 * BUTTON FUNCTION 2: Runs the actual sorter.
 *
 * Assign this function to your Run shape:
 * dailyLeadSorter
 */
function dailyLeadSorter() {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var cfg = LEAD_SORTER_CONFIG;
  var props = PropertiesService.getDocumentProperties();
  var runId = createRunId_();

  // Store the ID immediately. If the script stops after making some changes,
  // Undo Last Run can still find rows tagged by this run.
  props.setProperty(cfg.LAST_RUN_ID_PROPERTY, runId);
  props.setProperty(cfg.LAST_RUN_STATUS_PROPERTY, "RUNNING");

  try {
    var today = getTodayKey_(ss);

    var finalSheet = requireSheet_(ss, cfg.FINAL_SHEET);
    var noEmailSheet = requireSheet_(ss, cfg.NO_EMAIL_SHEET);
    var lessFollowersSheet = requireSheet_(ss, cfg.LESS_FOLLOWERS_SHEET);

    prepareManagedSheet_(finalSheet, cfg);
    prepareManagedSheet_(noEmailSheet, cfg);
    prepareManagedSheet_(lessFollowersSheet, cfg);

    // HashSet of emails that already existed in Final List before this run.
    // Source processing updates it only after a new lead is accepted, which
    // prevents duplicates within the same execution without changing appendRows.
    var existingFinalEmails = Object.create(null);
    if (finalSheet.getLastRow() > 1) {
      var fv = finalSheet
        .getRange(
          2,
          1,
          finalSheet.getLastRow() - 1,
          Math.max(finalSheet.getLastColumn(), cfg.OUTPUT_COLUMNS),
        )
        .getValues();
      var fh = finalSheet
        .getRange(
          1,
          1,
          1,
          Math.max(finalSheet.getLastColumn(), cfg.OUTPUT_COLUMNS),
        )
        .getValues()[0];
      var emailCol = findHeaderIndex_(fh, ["Email (Required)", "Email"], 1);
      fv.forEach(function (r) {
        var e = normalizeEmail_(r[emailCol]);
        if (e) existingFinalEmails[e] = true;
      });
    }

    var summary = {
      runId: runId,
      totalProcessed: 0,
      sentToFinalInitially: 0,
      returnedHistoricalDuplicates: 0,
      finalNetAdded: 0,
      sentToNoEmail: 0,
      sentToLessFollowers: 0,
      leftInSourceNoSocial: 0,
    };

    var finalBatch = [];
    var noEmailBatch = [];
    var lessFollowersBatch = [];
    var rowsToDeleteBySheet = {};
    var sourceReviewUpdates = {};

    cfg.SOURCE_SHEETS.forEach(function (sheetName) {
      var sheet = ss.getSheetByName(sheetName);
      if (!sheet || sheet.getLastRow() < 2) return;

      prepareManagedSheet_(sheet, cfg);

      var lastRow = sheet.getLastRow();
      var lastColumn = Math.max(sheet.getLastColumn(), cfg.OUTPUT_COLUMNS);
      var values = sheet.getRange(1, 1, lastRow, lastColumn).getValues();
      var headers = values[0];
      var indexes = getLeadColumnIndexes_(headers);
      var rowsToDelete = [];
      var reviewUpdates = [];

      for (var i = 1; i < values.length; i++) {
        var originalRow = values[i];
        var sheetRowNumber = i + 1;

        if (isBlankRow_(originalRow) || isStructuralRow_(originalRow)) {
          continue;
        }

        summary.totalProcessed++;

        var email = cleanText_(originalRow[indexes.email]);
        var instagram = cleanText_(originalRow[indexes.instagram]);
        var tiktok = cleanText_(originalRow[indexes.tiktok]);
        var followerRaw = getFollowerRaw_(originalRow, indexes);
        var followerAssessment = assessFollowers_(
          followerRaw,
          cfg.FOLLOWER_THRESHOLD,
        );

        var outputRow = normalizeRowWidth_(originalRow, cfg.OUTPUT_COLUMNS);

        // Save old review text so Undo can put it back.
        outputRow[cfg.PREVIOUS_REMARKS_INDEX] =
          originalRow[cfg.REMARKS_INDEX] || "";
        outputRow[cfg.PREVIOUS_FIX_INDEX] =
          originalRow[cfg.SUGGESTED_FIX_INDEX] || "";

        outputRow[cfg.DATE_INDEX] = today;
        outputRow[cfg.SOURCE_INDEX] = sheetName;
        outputRow[cfg.RUN_ID_INDEX] = runId;
        outputRow[cfg.REMARKS_INDEX] = "";
        outputRow[cfg.SUGGESTED_FIX_INDEX] = "";

        if (email === "") {
          outputRow[cfg.UPDATED_INDEX] = "";
          noEmailBatch.push(outputRow);
          rowsToDelete.push(sheetRowNumber);
          summary.sentToNoEmail++;
          continue;
        }

        if (followerAssessment.routeToLessFollowers) {
          outputRow[cfg.UPDATED_INDEX] = "";
          lessFollowersBatch.push(outputRow);
          rowsToDelete.push(sheetRowNumber);
          summary.sentToLessFollowers++;
          continue;
        }

        var hasSocialLink = instagram !== "" || tiktok !== "";
        if (hasSocialLink) {
          var emailKey = normalizeEmail_(email);
          if (emailKey && existingFinalEmails[emailKey]) {
            reviewUpdates.push({
              rowNumber: sheetRowNumber,
              values: [
                "Not moved: Email already exists in Final List.",
                "Duplicate lead. Verify before importing.",
                runId,
                originalRow[cfg.REMARKS_INDEX] || "",
                originalRow[cfg.SUGGESTED_FIX_INDEX] || "",
              ],
            });
            continue;
          }
          if (emailKey) existingFinalEmails[emailKey] = true;
          outputRow[cfg.UPDATED_INDEX] = "no";
          finalBatch.push(outputRow);
          rowsToDelete.push(sheetRowNumber);
          summary.sentToFinalInitially++;
        } else {
          // This row stays in its source sheet. Save its previous review values
          // in hidden helper columns and add clear review guidance.
          reviewUpdates.push({
            rowNumber: sheetRowNumber,
            values: [
              "Not moved: Instagram and TikTok links are both missing.",
              "Add at least one valid Instagram or TikTok profile link.",
              runId,
              originalRow[cfg.REMARKS_INDEX] || "",
              originalRow[cfg.SUGGESTED_FIX_INDEX] || "",
            ],
          });
          summary.leftInSourceNoSocial++;
        }
      }

      rowsToDeleteBySheet[sheetName] = rowsToDelete;
      sourceReviewUpdates[sheetName] = reviewUpdates;
    });

    // Add Remarks/Suggested Fix to rows that remain in source before deleting
    // other source rows. The values remain attached to the correct rows as rows shift.
    Object.keys(sourceReviewUpdates).forEach(function (sheetName) {
      var sheet = ss.getSheetByName(sheetName);
      applyReviewUpdates_(sheet, sourceReviewUpdates[sheetName], cfg);
    });

    // Append first. Source rows are deleted only after destination writes succeed.
    appendRows_(finalSheet, finalBatch, cfg.OUTPUT_COLUMNS);
    appendRows_(noEmailSheet, noEmailBatch, cfg.OUTPUT_COLUMNS);
    appendRows_(lessFollowersSheet, lessFollowersBatch, cfg.OUTPUT_COLUMNS);

    cfg.SOURCE_SHEETS.forEach(function (sheetName) {
      var sourceSheet = ss.getSheetByName(sheetName);
      if (!sourceSheet) return;
      deleteRowsInGroups_(sourceSheet, rowsToDeleteBySheet[sheetName] || []);
    });

    SpreadsheetApp.flush();

    summary.returnedHistoricalDuplicates = returnHistoricalDuplicates_(
      ss,
      finalSheet,
      today,
      runId,
      cfg,
    );

    summary.finalNetAdded =
      summary.sentToFinalInitially - summary.returnedHistoricalDuplicates;

    writeExecutionSummary_(ss, today, summary, cfg.SUMMARY_SHEET);

    props.setProperty(cfg.LAST_RUN_STATUS_PROPERTY, "COMPLETE");

    showMessage_(
      "Lead Sorter Complete",
      [
        "Total scanned: " + summary.totalProcessed,
        "Net added to Final List: " + summary.finalNetAdded,
        "Moved to Less Followers: " + summary.sentToLessFollowers,
        "Moved to No Emails Leads: " + summary.sentToNoEmail,
        "Left in source for social-link review: " +
          summary.leftInSourceNoSocial,
        "Historical duplicates returned: " +
          summary.returnedHistoricalDuplicates,
        "",
        "Undo is available for this run until the next sorter run.",
      ].join("\n"),
    );
  } catch (error) {
    props.setProperty(cfg.LAST_RUN_STATUS_PROPERTY, "FAILED_OR_PARTIAL");
    throw error;
  } finally {
    lock.releaseLock();
  }
}

/**
 * BUTTON FUNCTION 3: Reverses the latest sorter run.
 *
 * Assign this function to your Undo shape:
 * undoLastLeadSorterRun
 *
 * Note: Restored rows are appended to the bottom of their original source
 * sheet. Their original data is restored, but their exact old row position is
 * not guaranteed.
 */
function undoLastLeadSorterRun() {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);

  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var cfg = LEAD_SORTER_CONFIG;
    var props = PropertiesService.getDocumentProperties();
    var runId = props.getProperty(cfg.LAST_RUN_ID_PROPERTY);

    if (!runId) {
      showMessage_(
        "Undo Last Run",
        "There is no lead-sorter run available to undo.",
      );
      return;
    }

    var restoredFromDestinations = 0;
    var sourceRowsReset = 0;
    var summaryRowsRemoved = 0;
    var skippedRows = 0;

    var destinationNames = [
      cfg.FINAL_SHEET,
      cfg.NO_EMAIL_SHEET,
      cfg.LESS_FOLLOWERS_SHEET,
    ];

    // 1. Move rows created by the last run from destination sheets back to
    // their recorded source sheets, then delete those destination rows.
    destinationNames.forEach(function (destinationName) {
      var destinationSheet = ss.getSheetByName(destinationName);
      if (!destinationSheet || destinationSheet.getLastRow() < 2) return;

      prepareManagedSheet_(destinationSheet, cfg);

      var width = Math.max(
        destinationSheet.getLastColumn(),
        cfg.OUTPUT_COLUMNS,
      );
      var values = destinationSheet
        .getRange(1, 1, destinationSheet.getLastRow(), width)
        .getValues();
      var restoreBatches = {};
      var rowsToDelete = [];

      for (var i = 1; i < values.length; i++) {
        var row = values[i];
        if (cleanText_(row[cfg.RUN_ID_INDEX]) !== runId) continue;

        var sourceName = cleanText_(row[cfg.SOURCE_INDEX]);
        var sourceSheet = ss.getSheetByName(sourceName);

        if (!sourceSheet || cfg.SOURCE_SHEETS.indexOf(sourceName) === -1) {
          skippedRows++;
          continue;
        }

        prepareManagedSheet_(sourceSheet, cfg);

        var restoredRow = normalizeRowWidth_(row, cfg.OUTPUT_COLUMNS);
        restoredRow[cfg.DATE_INDEX] = "";
        restoredRow[cfg.UPDATED_INDEX] = "";
        restoredRow[cfg.SOURCE_INDEX] = "";
        restoredRow[cfg.REMARKS_INDEX] =
          restoredRow[cfg.PREVIOUS_REMARKS_INDEX] || "";
        restoredRow[cfg.SUGGESTED_FIX_INDEX] =
          restoredRow[cfg.PREVIOUS_FIX_INDEX] || "";
        restoredRow[cfg.RUN_ID_INDEX] = "";
        restoredRow[cfg.PREVIOUS_REMARKS_INDEX] = "";
        restoredRow[cfg.PREVIOUS_FIX_INDEX] = "";

        if (!restoreBatches[sourceName]) restoreBatches[sourceName] = [];
        restoreBatches[sourceName].push(restoredRow);
        rowsToDelete.push(i + 1);
      }

      Object.keys(restoreBatches).forEach(function (sourceName) {
        appendRows_(
          ss.getSheetByName(sourceName),
          restoreBatches[sourceName],
          cfg.OUTPUT_COLUMNS,
        );
        restoredFromDestinations += restoreBatches[sourceName].length;
      });

      SpreadsheetApp.flush();
      deleteRowsInGroups_(destinationSheet, rowsToDelete);
    });

    // 2. Rows that stayed in source, including historical duplicates returned
    // during the run, are already in the correct sheet. Restore their previous
    // Remarks/Suggested Fix and remove the hidden run markers.
    cfg.SOURCE_SHEETS.forEach(function (sheetName) {
      var sheet = ss.getSheetByName(sheetName);
      if (!sheet || sheet.getLastRow() < 2) return;

      prepareManagedSheet_(sheet, cfg);

      var width = Math.max(sheet.getLastColumn(), cfg.OUTPUT_COLUMNS);
      var values = sheet.getRange(1, 1, sheet.getLastRow(), width).getValues();
      var resetUpdates = [];

      for (var i = 1; i < values.length; i++) {
        if (cleanText_(values[i][cfg.RUN_ID_INDEX]) !== runId) continue;

        resetUpdates.push({
          rowNumber: i + 1,
          values: [
            values[i][cfg.PREVIOUS_REMARKS_INDEX] || "",
            values[i][cfg.PREVIOUS_FIX_INDEX] || "",
            "",
            "",
            "",
          ],
        });
        sourceRowsReset++;
      }

      // Write only actual lead rows, grouped into batch writes.
      // This avoids touching merged date rows and reduces Spreadsheet calls.
      applyReviewUpdates_(sheet, resetUpdates, cfg);
    });

    // 3. Remove the summary entry created by this run.
    var summarySheet = ss.getSheetByName(cfg.SUMMARY_SHEET);
    if (summarySheet && summarySheet.getLastRow() >= 2) {
      var summaryValues = summarySheet
        .getRange(1, 1, summarySheet.getLastRow(), summarySheet.getLastColumn())
        .getValues();
      var summaryHeaders = summaryValues[0];
      var runIdIndex = findHeaderIndex_(summaryHeaders, ["Run ID"], 8);
      var summaryRowsToDelete = [];

      for (var s = 1; s < summaryValues.length; s++) {
        if (cleanText_(summaryValues[s][runIdIndex]) === runId) {
          summaryRowsToDelete.push(s + 1);
        }
      }

      summaryRowsRemoved = summaryRowsToDelete.length;
      deleteRowsInGroups_(summarySheet, summaryRowsToDelete);
    }

    props.deleteProperty(cfg.LAST_RUN_ID_PROPERTY);
    props.deleteProperty(cfg.LAST_RUN_STATUS_PROPERTY);

    showMessage_(
      "Undo Complete",
      [
        "Rows restored from destination sheets: " + restoredFromDestinations,
        "Rows reset in source sheets: " + sourceRowsReset,
        "Execution Summary rows removed: " + summaryRowsRemoved,
        "Rows skipped because their source sheet was invalid: " + skippedRows,
        "",
        "Restored rows are placed at the bottom of their original source sheets.",
      ].join("\n"),
    );
  } finally {
    lock.releaseLock();
  }
}

/**
 * Finds rows added to Final List by the current run whose email already
 * appeared on an earlier date. The duplicate row is returned to its source
 * with a Remark and Suggested Fix.
 */
function returnHistoricalDuplicates_(ss, finalSheet, today, runId, cfg) {
  var lastRow = finalSheet.getLastRow();
  if (lastRow < 2) return 0;

  prepareManagedSheet_(finalSheet, cfg);

  var lastColumn = Math.max(finalSheet.getLastColumn(), cfg.OUTPUT_COLUMNS);
  var values = finalSheet.getRange(1, 1, lastRow, lastColumn).getValues();
  var headers = values[0];

  var emailIndex = findHeaderIndex_(headers, ["Email (Required)", "Email"], 1);
  var dateIndex = findHeaderIndex_(headers, ["Date"], cfg.DATE_INDEX);
  var sourceIndex = findHeaderIndex_(
    headers,
    ["Source Sheet Name", "Source Sheet", "Source"],
    cfg.SOURCE_INDEX,
  );
  var runIdIndex = findHeaderIndex_(
    headers,
    ["Lead Sorter Run ID"],
    cfg.RUN_ID_INDEX,
  );

  var historicalEmails = {};

  for (var i = 1; i < values.length; i++) {
    var row = values[i];
    var email = normalizeEmail_(row[emailIndex]);
    var dateKey = normalizeDateKey_(row[dateIndex], ss);

    if (email && isPastDateKey_(dateKey, today)) {
      historicalEmails[email] = true;
    }
  }

  var restoreBatches = {};
  var finalRowsToDelete = [];

  for (var j = 1; j < values.length; j++) {
    var currentRow = values[j];
    var currentEmail = normalizeEmail_(currentRow[emailIndex]);
    var currentDate = normalizeDateKey_(currentRow[dateIndex], ss);
    var currentRunId = cleanText_(currentRow[runIdIndex]);

    if (
      currentRunId === runId &&
      currentDate === today &&
      currentEmail &&
      historicalEmails[currentEmail]
    ) {
      var sourceName = cleanText_(currentRow[sourceIndex]);
      var sourceSheet = ss.getSheetByName(sourceName);

      if (!sourceSheet || cfg.SOURCE_SHEETS.indexOf(sourceName) === -1) {
        Logger.log(
          "Duplicate not returned because source sheet is missing/invalid: " +
            sourceName +
            " | " +
            currentEmail,
        );
        continue;
      }

      prepareManagedSheet_(sourceSheet, cfg);

      var restoredRow = normalizeRowWidth_(currentRow, cfg.OUTPUT_COLUMNS);
      restoredRow[cfg.DATE_INDEX] = "";
      restoredRow[cfg.UPDATED_INDEX] = "";
      restoredRow[cfg.SOURCE_INDEX] = "";
      restoredRow[cfg.REMARKS_INDEX] =
        "Not moved: This email already exists in Final List from an earlier date.";
      restoredRow[cfg.SUGGESTED_FIX_INDEX] =
        "Review the older lead. Keep this row only if it is genuinely different and has a different verified email.";
      restoredRow[cfg.RUN_ID_INDEX] = runId;
      // PREVIOUS_REMARKS and PREVIOUS_FIX remain preserved for Undo.

      if (!restoreBatches[sourceName]) restoreBatches[sourceName] = [];
      restoreBatches[sourceName].push(restoredRow);
      finalRowsToDelete.push(j + 1);
    }
  }

  Object.keys(restoreBatches).forEach(function (sourceName) {
    appendRows_(
      ss.getSheetByName(sourceName),
      restoreBatches[sourceName],
      cfg.OUTPUT_COLUMNS,
    );
  });

  SpreadsheetApp.flush();
  deleteRowsInGroups_(finalSheet, finalRowsToDelete);

  return finalRowsToDelete.length;
}

function writePreviewSheet_(ss, today, summary, detailRows, cfg) {
  var sheet = ss.getSheetByName(cfg.PREVIEW_SHEET);
  if (!sheet) sheet = ss.insertSheet(cfg.PREVIEW_SHEET);

  try {
    sheet.getDataRange().breakApart();
  } catch (ignore) {}
  sheet.clear();

  var summaryData = [
    ["Lead Sorter Preview", ""],
    ["Preview Date", today],
    ["Nothing moved", "Yes"],
    ["Total Leads Scanned", summary.total],
    ["Would Move to Final List", summary.finalList],
    ["Would Move to No Emails Leads", summary.noEmail],
    ["Would Move to Less Followers", summary.lessFollowers],
    ["Would Remain/Return to Source", summary.staysInSource],
    ["Historical Duplicates", summary.historicalDuplicates],
  ];

  sheet.getRange(1, 1, summaryData.length, 2).setValues(summaryData);
  sheet.getRange("A1:B1").merge();
  sheet
    .getRange("A1:B1")
    .setFontWeight("bold")
    .setFontSize(14)
    .setHorizontalAlignment("center")
    .setBackground("#4A86E8")
    .setFontColor("#FFFFFF");
  sheet.getRange(2, 1, summaryData.length - 1, 1).setFontWeight("bold");

  var startRow = summaryData.length + 2;
  var headers = [
    "Source Sheet",
    "Source Row",
    "Name",
    "Email",
    "Followers",
    "Instagram",
    "TikTok",
    "Planned Action",
    "Remark",
    "Suggested Fix",
  ];

  sheet.getRange(startRow, 1, 1, headers.length).setValues([headers]);
  sheet
    .getRange(startRow, 1, 1, headers.length)
    .setFontWeight("bold")
    .setBackground("#D9EAF7")
    .setHorizontalAlignment("center");

  if (detailRows.length > 0) {
    sheet
      .getRange(startRow + 1, 1, detailRows.length, headers.length)
      .setValues(detailRows);
  }

  sheet.setFrozenRows(startRow);
  sheet.autoResizeColumns(1, headers.length);
  sheet.setColumnWidth(8, 230);
  sheet.setColumnWidth(9, 330);
  sheet.setColumnWidth(10, 380);
  sheet.getDataRange().setWrap(true).setVerticalAlignment("top");

  sheet.activate();
}

function writeExecutionSummary_(ss, date, summary, summarySheetName) {
  var sheet = ss.getSheetByName(summarySheetName);

  if (!sheet) {
    sheet = ss.insertSheet(summarySheetName);
  }

  var headers = [
    "Date",
    "Total Leads Scanned",
    "Initially Moved to Final List",
    "Historical Duplicates Returned",
    "Net Added to Final List",
    "Moved to Less Followers",
    "Moved to No Emails Leads",
    "Left in Source: No Social Link",
    "Run ID",
  ];

  if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  } else {
    ensureColumnCount_(sheet, headers.length);
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  }

  sheet
    .getRange(1, 1, 1, headers.length)
    .setFontWeight("bold")
    .setBackground("#4A86E8")
    .setFontColor("#FFFFFF")
    .setHorizontalAlignment("center");
  sheet.setFrozenRows(1);

  sheet.appendRow([
    date,
    summary.totalProcessed,
    summary.sentToFinalInitially,
    summary.returnedHistoricalDuplicates,
    summary.finalNetAdded,
    summary.sentToLessFollowers,
    summary.sentToNoEmail,
    summary.leftInSourceNoSocial,
    summary.runId,
  ]);

  // Avoid auto-resizing every run because it can be slow on large sheets.

  // Run ID is technical information required for Undo; keep it hidden.
  try {
    sheet.hideColumns(9);
  } catch (ignore) {}
}

function getHistoricalFinalEmails_(ss, today, cfg) {
  var sheet = ss.getSheetByName(cfg.FINAL_SHEET);
  var emails = {};
  if (!sheet || sheet.getLastRow() < 2) return emails;

  var values = sheet
    .getRange(1, 1, sheet.getLastRow(), Math.max(sheet.getLastColumn(), 1))
    .getValues();
  var headers = values[0];
  var emailIndex = findHeaderIndex_(headers, ["Email (Required)", "Email"], 1);
  var dateIndex = findHeaderIndex_(headers, ["Date"], cfg.DATE_INDEX);

  for (var i = 1; i < values.length; i++) {
    var email = normalizeEmail_(values[i][emailIndex]);
    var dateKey = normalizeDateKey_(values[i][dateIndex], ss);
    if (email && isPastDateKey_(dateKey, today)) emails[email] = true;
  }

  return emails;
}

function prepareManagedSheet_(sheet, cfg) {
  ensureColumnCount_(sheet, cfg.OUTPUT_COLUMNS);

  var headers = sheet.getRange(1, 1, 1, cfg.OUTPUT_COLUMNS).getValues()[0];

  headers[cfg.DATE_INDEX] = headers[cfg.DATE_INDEX] || "Date";
  headers[cfg.UPDATED_INDEX] = headers[cfg.UPDATED_INDEX] || "updated";
  headers[cfg.SOURCE_INDEX] = headers[cfg.SOURCE_INDEX] || "Source Sheet Name";
  headers[cfg.REMARKS_INDEX] = "Remarks";
  headers[cfg.SUGGESTED_FIX_INDEX] = "Suggested Fix";
  headers[cfg.RUN_ID_INDEX] = "Lead Sorter Run ID";
  headers[cfg.PREVIOUS_REMARKS_INDEX] = "Previous Remarks";
  headers[cfg.PREVIOUS_FIX_INDEX] = "Previous Suggested Fix";

  sheet.getRange(1, 1, 1, cfg.OUTPUT_COLUMNS).setValues([headers]);

  // Hide only the technical Undo columns. Remarks and Suggested Fix remain visible.
  try {
    sheet.hideColumns(cfg.RUN_ID_INDEX + 1, 3);
  } catch (ignore) {}
}

function applyReviewUpdates_(sheet, updates, cfg) {
  if (!sheet || !updates || updates.length === 0) return;

  // Batch consecutive row updates into one Spreadsheet write per group.
  // This is much faster than calling setValues once for every lead.
  updates.sort(function (a, b) {
    return a.rowNumber - b.rowNumber;
  });

  var groupStart = updates[0].rowNumber;
  var previousRow = updates[0].rowNumber;
  var groupValues = [updates[0].values];

  function writeCurrentGroup_() {
    sheet
      .getRange(groupStart, cfg.REMARKS_INDEX + 1, groupValues.length, 5)
      .setValues(groupValues);
  }

  for (var i = 1; i < updates.length; i++) {
    var update = updates[i];

    if (update.rowNumber === previousRow + 1) {
      groupValues.push(update.values);
    } else {
      writeCurrentGroup_();
      groupStart = update.rowNumber;
      groupValues = [update.values];
    }

    previousRow = update.rowNumber;
  }

  writeCurrentGroup_();
}

function getLeadColumnIndexes_(headers) {
  return {
    email: findHeaderIndex_(headers, ["Email (Required)", "Email"], 1),
    instagram: findHeaderIndex_(headers, ["Instagram"], 5),
    tiktok: findHeaderIndex_(headers, ["TikTok", "Tiktok"], 6),
    exactFollowers: findHeaderIndex_(
      headers,
      ["Follower Count", "Followers Count", "Exact Followers", "Followers"],
      -1,
    ),
    followerBucket: findHeaderIndex_(
      headers,
      ["Followers Bucket", "Follower Bucket"],
      15,
    ),
  };
}

function getFollowerRaw_(row, indexes) {
  if (
    indexes.exactFollowers >= 0 &&
    cleanText_(row[indexes.exactFollowers]) !== ""
  ) {
    return row[indexes.exactFollowers];
  }
  return row[indexes.followerBucket];
}

function assessFollowers_(value, threshold) {
  var bounds = parseFollowerBounds_(value);

  if (bounds.min === null && bounds.max === null) {
    return { routeToLessFollowers: true, reason: "missing", bounds: bounds };
  }

  if (bounds.max !== null && bounds.max < threshold) {
    return { routeToLessFollowers: true, reason: "below", bounds: bounds };
  }

  if (bounds.min !== null && bounds.min >= threshold) {
    return { routeToLessFollowers: false, reason: "qualified", bounds: bounds };
  }

  return { routeToLessFollowers: true, reason: "ambiguous", bounds: bounds };
}

function appendRows_(sheet, rows, width) {
  if (!rows || rows.length === 0) return;

  ensureColumnCount_(sheet, width);

  var normalizedRows = rows.map(function (row) {
    return normalizeRowWidth_(row, width);
  });

  sheet
    .getRange(sheet.getLastRow() + 1, 1, normalizedRows.length, width)
    .setValues(normalizedRows);
}

function ensureColumnCount_(sheet, requiredColumns) {
  var currentColumns = sheet.getMaxColumns();
  if (currentColumns < requiredColumns) {
    sheet.insertColumnsAfter(currentColumns, requiredColumns - currentColumns);
  }
}

/** Delete row groups from bottom to top so row numbers do not shift. */
function deleteRowsInGroups_(sheet, rowNumbers) {
  if (!rowNumbers || rowNumbers.length === 0) return;

  var unique = {};
  rowNumbers.forEach(function (rowNumber) {
    unique[rowNumber] = true;
  });

  var sorted = Object.keys(unique)
    .map(function (key) {
      return Number(key);
    })
    .sort(function (a, b) {
      return a - b;
    });

  if (sorted.length === 0) return;

  var groups = [];
  var start = sorted[0];
  var previous = sorted[0];

  for (var i = 1; i < sorted.length; i++) {
    if (sorted[i] === previous + 1) {
      previous = sorted[i];
    } else {
      groups.push({ start: start, count: previous - start + 1 });
      start = sorted[i];
      previous = sorted[i];
    }
  }
  groups.push({ start: start, count: previous - start + 1 });

  for (var g = groups.length - 1; g >= 0; g--) {
    sheet.deleteRows(groups[g].start, groups[g].count);
  }
}

function requireSheet_(ss, sheetName) {
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    throw new Error('Required sheet not found: "' + sheetName + '"');
  }
  return sheet;
}

function findHeaderIndex_(headers, acceptedNames, fallbackIndex) {
  var normalizedHeaders = headers.map(function (header) {
    return cleanText_(header).toLowerCase();
  });

  for (var i = 0; i < acceptedNames.length; i++) {
    var wanted = acceptedNames[i].toLowerCase();
    var index = normalizedHeaders.indexOf(wanted);
    if (index !== -1) return index;
  }

  return fallbackIndex;
}

function normalizeRowWidth_(row, width) {
  var output = row.slice(0, width);
  while (output.length < width) output.push("");
  return output;
}

function cleanText_(value) {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function normalizeEmail_(value) {
  return cleanText_(value).toLowerCase();
}

function isBlankRow_(row) {
  for (var i = 0; i < row.length; i++) {
    if (cleanText_(row[i]) !== "") return false;
  }
  return true;
}

function isStructuralRow_(row) {
  var firstCell = cleanText_(row[0]).toLowerCase();
  return (
    firstCell.indexOf("date:-") === 0 ||
    firstCell.indexOf("date:") === 0 ||
    firstCell === "name (required)" ||
    firstCell === "name"
  );
}

function isPastDateKey_(dateKey, today) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateKey)) return false;
  return dateKey < today;
}

function normalizeDateKey_(value, ss) {
  if (value instanceof Date && !isNaN(value.getTime())) {
    return Utilities.formatDate(
      value,
      ss.getSpreadsheetTimeZone(),
      "yyyy-MM-dd",
    );
  }

  var text = cleanText_(value);
  if (!text) return "";

  var exact = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (exact) return text;

  var parsed = new Date(text);
  if (!isNaN(parsed.getTime())) {
    return Utilities.formatDate(
      parsed,
      ss.getSpreadsheetTimeZone(),
      "yyyy-MM-dd",
    );
  }

  return text;
}

function parseFollowerBounds_(value) {
  if (value === null || value === undefined || cleanText_(value) === "") {
    return { min: null, max: null };
  }

  if (typeof value === "number" && !isNaN(value)) {
    return { min: value, max: value };
  }

  var text = cleanText_(value).toLowerCase().replace(/,/g, "");
  var numbers = text.match(/\d+(?:\.\d+)?\s*[km]?/g) || [];
  var parsedNumbers = numbers
    .map(parseCompactFollowerNumber_)
    .filter(function (number) {
      return number !== null;
    });

  if (parsedNumbers.length === 0) {
    return { min: null, max: null };
  }

  if (/less than|under|below|</.test(text)) {
    return { min: 0, max: Math.max(0, parsedNumbers[0] - 1) };
  }

  if (/more than|over|above|\+|>/.test(text)) {
    return { min: parsedNumbers[0], max: null };
  }

  if (parsedNumbers.length >= 2 && /\bto\b|-/.test(text)) {
    return {
      min: Math.min(parsedNumbers[0], parsedNumbers[1]),
      max: Math.max(parsedNumbers[0], parsedNumbers[1]),
    };
  }

  return { min: parsedNumbers[0], max: parsedNumbers[0] };
}

function parseCompactFollowerNumber_(token) {
  if (!token) return null;

  var cleaned = token.toLowerCase().replace(/\s+/g, "");
  var multiplier = 1;

  if (cleaned.indexOf("k") !== -1) multiplier = 1000;
  if (cleaned.indexOf("m") !== -1) multiplier = 1000000;

  var numericPart = parseFloat(cleaned.replace(/[km]/g, ""));
  return isNaN(numericPart) ? null : numericPart * multiplier;
}

function getTodayKey_(ss) {
  return Utilities.formatDate(
    new Date(),
    ss.getSpreadsheetTimeZone(),
    "yyyy-MM-dd",
  );
}

function createRunId_() {
  return (
    Utilities.formatDate(
      new Date(),
      Session.getScriptTimeZone(),
      "yyyyMMdd_HHmmss",
    ) +
    "_" +
    Math.floor(Math.random() * 1000000)
  );
}

/**
 * Displays a centred completion popup.
 *
 * This function is used only after:
 * 1. dailyLeadSorter()
 * 2. undoLastLeadSorterRun()
 *
 * Preview does not call this function.
 */
function showMessage_(title, message) {
  try {
    var safeTitle = escapeHtml_(title);
    var safeMessage = escapeHtml_(message).replace(/\n/g, "<br>");

    var htmlContent =
      "<!DOCTYPE html>" +
      "<html>" +
      "<head>" +
      '<base target="_top">' +
      "<style>" +
      "body {" +
      "  font-family: Arial, sans-serif;" +
      "  margin: 0;" +
      "  padding: 22px;" +
      "  color: #202124;" +
      "  background: #ffffff;" +
      "}" +
      "h2 {" +
      "  font-size: 19px;" +
      "  margin: 0 0 14px 0;" +
      "  color: #202124;" +
      "}" +
      ".message {" +
      "  font-size: 15px;" +
      "  line-height: 1.5;" +
      "  max-height: 260px;" +
      "  overflow-y: auto;" +
      "}" +
      ".actions {" +
      "  text-align: right;" +
      "  margin-top: 22px;" +
      "}" +
      "button {" +
      "  background: #1a73e8;" +
      "  color: #ffffff;" +
      "  border: none;" +
      "  border-radius: 4px;" +
      "  padding: 9px 24px;" +
      "  font-size: 14px;" +
      "  cursor: pointer;" +
      "}" +
      "button:hover {" +
      "  background: #1558b0;" +
      "}" +
      "</style>" +
      "</head>" +
      "<body>" +
      "<h2>" +
      safeTitle +
      "</h2>" +
      '<div class="message">' +
      safeMessage +
      "</div>" +
      '<div class="actions">' +
      '<button onclick="google.script.host.close()">OK</button>' +
      "</div>" +
      "</body>" +
      "</html>";

    var html = HtmlService.createHtmlOutput(htmlContent)
      .setWidth(470)
      .setHeight(360);

    SpreadsheetApp.getUi().showModalDialog(html, title);
  } catch (error) {
    console.log(title + "\n" + message + "\n" + error);
  }
}

/**
 * Prevents special characters in messages from breaking the popup HTML.
 */
function escapeHtml_(value) {
  return String(value === null || value === undefined ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
